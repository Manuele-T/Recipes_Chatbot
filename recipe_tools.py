import pandas as pd
import traceback
# import numpy as np # Not strictly needed for the fix unless using np.ndarray explicitly elsewhere

# This global DataFrame will be populated by main.py on application startup
recipes_df: pd.DataFrame | None = None

def set_recipes_dataframe(df: pd.DataFrame):
    """
    This function will be called from main.py once the DataFrame is loaded from GCS.
    """
    global recipes_df
    recipes_df = df
    if recipes_df is not None and not recipes_df.empty:
        print(f"Recipe DataFrame successfully loaded into recipe_tools. Shape: {recipes_df.shape}")
    elif recipes_df is not None and recipes_df.empty:
        print(f"Recipe DataFrame initialized as EMPTY in recipe_tools. Shape: {recipes_df.shape}. This might be due to a loading error upstream.")
    else:
        print("Failed to initialize DataFrame in recipe_tools (it's None).")

def format_results_for_gemini(filtered_df: pd.DataFrame, max_results: int = 3) -> str:
    """
    Formats a DataFrame of recipes into a string suitable for Gemini.
    """
    if filtered_df.empty:
        return "No recipes found matching your criteria."

    output_parts = ["Here are some recipes I found:"]
    
    display_columns = [
        'Name', 'RecipeInstructions', 'Calories', 'RecipeCategory', 
        'RecipeIngredientParts', 'SodiumContent', 'Keywords', 'TotalTime'
    ]
    # Ensure we only try to access columns that actually exist in the filtered_df
    available_columns = [col for col in display_columns if col in filtered_df.columns]

    for index, row in filtered_df[available_columns].head(max_results).iterrows():
        recipe_detail = f"\n### {row.get('Name', 'N/A')}" 
        
        if 'RecipeCategory' in row and pd.notna(row['RecipeCategory']):
            recipe_detail += f"\n*Category:* {row['RecipeCategory']}"
        
        if 'Calories' in row and pd.notna(row['Calories']):
            recipe_detail += f"\n*Calories:* {row.get('Calories')}"

        if 'SodiumContent' in row and pd.notna(row['SodiumContent']):
            recipe_detail += f"\n*Sodium:* {row.get('SodiumContent')} mg"

        if 'TotalTime' in row and pd.notna(row['TotalTime']):
            recipe_detail += f"\n*Cook Time:* {row.get('TotalTime')} minutes"

        if 'Keywords' in row and isinstance(row['Keywords'], list) and row['Keywords']:
            keywords_str = [str(kw) for kw in row['Keywords'][:3]]
            recipe_detail += f"\n*Cuisine/Keywords:* {', '.join(keywords_str)}{'...' if len(row['Keywords']) > 3 else ''}"

        if 'RecipeIngredientParts' in row and isinstance(row['RecipeIngredientParts'], list) and row['RecipeIngredientParts']:
            key_ingredients = [str(ing) for ing in row['RecipeIngredientParts'][:5]] 
            recipe_detail += f"\n*Key Ingredients:* {', '.join(key_ingredients)}{'...' if len(row['RecipeIngredientParts']) > 5 else ''}"

        # --- MODIFIED SECTION for RecipeInstructions ---
        if 'RecipeInstructions' in row: # Check if column exists in the row's available columns
            instructions_value = row.get('RecipeInstructions')
            is_instructions_present = False
            if instructions_value is not None:
                # Check if it's a list, Pandas Series, or Pandas specific array type
                if isinstance(instructions_value, (list, pd.Series, pd.arrays.PandasArray)):
                    if isinstance(instructions_value, list):
                        # For a Python list, consider it present if it's not empty
                        is_instructions_present = bool(instructions_value)
                    else:
                        # For Pandas Series or PandasArray, consider it present if any element is not NA
                        # This requires converting to Series if it's a PandasArray for .notna().any()
                        is_instructions_present = pd.Series(instructions_value).notna().any()
                else:
                    # For scalar values (string, number, bool, etc.)
                    is_instructions_present = pd.notna(instructions_value)
            
            if is_instructions_present:
                instructions = str(instructions_value) # Convert to string (handles lists becoming "['Step1', 'Step2']")
                recipe_detail += f"\n*Instructions:* {instructions[:200] + '...' if len(instructions) > 200 else instructions}"
        # --- END MODIFIED SECTION ---
        
        output_parts.append(recipe_detail)
    
    if len(filtered_df) > max_results:
        output_parts.append(f"\n...and {len(filtered_df) - max_results} more similar recipes found.")
        
    return "\n".join(output_parts)

# --- Main Search Tool ---

def search_recipes_by_criteria_tool(
    ingredients: list[str] | None = None, 
    category: str | None = None, 
    max_calories: int | None = None,
    max_sodium: int | None = None, 
    cuisine: str | None = None,    
    max_cook_time: int | None = None, 
    recipe_name: str | None = None
) -> str:
    if recipes_df is None:
        return "I'm sorry, the recipe dataset is not available at the moment. Please try again later."

    filtered_df = recipes_df.copy()
    applied_filters = False

    def _check_column(df, col_name, filter_name):
        if col_name not in df.columns:
            print(f"Warning: Column '{col_name}' not found for '{filter_name}' filter.")
            return False
        return True

    if ingredients and isinstance(ingredients, list) and len(ingredients) > 0:
        applied_filters = True
        if not _check_column(filtered_df, 'RecipeIngredientParts', 'ingredients'):
            return "Cannot search by ingredients: 'RecipeIngredientParts' column is missing."
        try:
            ingredients_lower = [ing.lower() for ing in ingredients]
            # Ensure 'parts' is treated as a list and items within 'parts' are strings for robust searching
            condition = filtered_df['RecipeIngredientParts'].apply(
                lambda parts: isinstance(parts, list) and \
                              all(any(ing_search in str(item).lower() for item in parts if item is not None) for ing_search in ingredients_lower)
            )
            filtered_df = filtered_df[condition]
        except Exception as e:
            print(f"Error during ingredients filtering: {e}")
            traceback.print_exc() # Add traceback for debugging filter errors
            return f"An error occurred while searching by ingredients."
        if filtered_df.empty: return f"No recipes found containing all ingredients: {', '.join(ingredients)}."
    
    if recipe_name:
        applied_filters = True
        if not _check_column(filtered_df, 'Name', 'recipe name'):
            return "Cannot search by name: 'Name' column is missing."
        try:
            filtered_df = filtered_df[filtered_df['Name'].str.contains(recipe_name, case=False, na=False)]
        except Exception as e:
            print(f"Error during recipe name filtering: {e}")
            traceback.print_exc()
            return f"An error occurred while searching by recipe name."
        if filtered_df.empty: return f"No recipes found with the name/keyword: {recipe_name} (after other filters)."

    if category:
        applied_filters = True
        if not _check_column(filtered_df, 'RecipeCategory', 'category'):
            return "Cannot search by category: 'RecipeCategory' column is missing."
        try:
            filtered_df = filtered_df[filtered_df['RecipeCategory'].str.contains(category, case=False, na=False)]
        except Exception as e:
            print(f"Error during category filtering: {e}")
            traceback.print_exc()
            return f"An error occurred while searching by category."
        if filtered_df.empty: return f"No recipes found in category: {category} (after other filters)."

    if max_calories is not None:
        applied_filters = True
        if not _check_column(filtered_df, 'Calories', 'max calories'):
            return "Cannot filter by calories: 'Calories' column is missing."
        try:
            calories_numeric = pd.to_numeric(filtered_df['Calories'], errors='coerce')
            # Create a boolean Series for filtering, ensuring same index as filtered_df
            condition = pd.Series(False, index=filtered_df.index)
            valid_calories = calories_numeric.notna()
            condition[valid_calories] = calories_numeric[valid_calories] <= max_calories
            filtered_df = filtered_df[condition]

        except Exception as e:
            print(f"Error during calorie filtering: {e}")
            traceback.print_exc()
            return f"An error occurred while filtering by calories."
        if filtered_df.empty: return f"No recipes found under {max_calories} calories (after other filters)."

    if max_sodium is not None:
        applied_filters = True
        if not _check_column(filtered_df, 'SodiumContent', 'max sodium'):
            return "Cannot filter by sodium: 'SodiumContent' column is missing."
        try:
            sodium_numeric = pd.to_numeric(filtered_df['SodiumContent'], errors='coerce')
            condition = pd.Series(False, index=filtered_df.index)
            valid_sodium = sodium_numeric.notna()
            condition[valid_sodium] = sodium_numeric[valid_sodium] <= max_sodium
            filtered_df = filtered_df[condition]
        except Exception as e:
            print(f"Error during sodium filtering: {e}")
            traceback.print_exc()
            return f"An error occurred while filtering by sodium content."
        if filtered_df.empty: return f"No recipes found under {max_sodium}mg sodium (after other filters)."

    if cuisine:
        applied_filters = True
        if not _check_column(filtered_df, 'Keywords', 'cuisine/keywords'):
            return "Cannot search by cuisine: 'Keywords' column is missing."
        try:
            cuisine_lower = cuisine.lower()
            condition = filtered_df['Keywords'].apply(
                lambda kws: isinstance(kws, list) and \
                            any(cuisine_lower in str(kw).lower() for kw in kws if kw is not None)
            )
            filtered_df = filtered_df[condition]
        except Exception as e:
            print(f"Error during cuisine/keywords filtering: {e}")
            traceback.print_exc()
            return f"An error occurred while searching by cuisine."
        if filtered_df.empty: return f"No recipes found for cuisine/keyword: {cuisine} (after other filters)."

    if max_cook_time is not None:
        applied_filters = True
        if not _check_column(filtered_df, 'TotalTime', 'max cook time'):
            return "Cannot filter by cook time: 'TotalTime' column is missing."
        try:
            cook_time_numeric = pd.to_numeric(filtered_df['TotalTime'], errors='coerce')
            condition = pd.Series(False, index=filtered_df.index)
            valid_cook_time = cook_time_numeric.notna()
            condition[valid_cook_time] = cook_time_numeric[valid_cook_time] <= max_cook_time
            filtered_df = filtered_df[condition]
        except Exception as e:
            print(f"Error during cook time filtering: {e}")
            traceback.print_exc()
            return f"An error occurred while filtering by cook time."
        if filtered_df.empty: return f"No recipes found with cook time under {max_cook_time} minutes (after other filters)."
    
    if not applied_filters:
        return "Please provide some criteria to search for recipes (e.g., ingredients, category, name, max calories, cuisine, max cook time, max sodium)."
            
    return format_results_for_gemini(filtered_df)


def get_nutritional_info_tool(recipe_name: str) -> str:
    if recipes_df is None:
        return "I'm sorry, the recipe dataset is not available at the moment."

    try:
        if 'Name' not in recipes_df.columns:
            return "Information unavailable: 'Name' column missing."
        
        match = recipes_df[recipes_df['Name'].str.contains(recipe_name, case=False, na=False)]
        
        if match.empty:
            return f"Sorry, I couldn't find a recipe named '{recipe_name}' to get nutritional info."
        
        recipe_data = match.iloc[0]
        output_parts = [f"Nutritional information for '{recipe_data.get('Name', recipe_name)}':"]
        
        nutritional_columns = ['Calories', 'SodiumContent', 'FatContent', 'ProteinContent', 'CarbohydrateContent']
        for col in nutritional_columns:
            if col in recipe_data and pd.notna(recipe_data[col]):
                unit = " mg" if col == "SodiumContent" else ""
                output_parts.append(f"* {col.replace('Content', '')}: {recipe_data[col]}{unit}")
        
        if len(output_parts) == 1: 
            return f"No specific nutritional details found for '{recipe_data.get('Name', recipe_name)}', though the recipe exists."

        return "\n".join(output_parts)
        
    except Exception as e:
        print(f"Error in get_nutritional_info_tool for '{recipe_name}': {e}")
        traceback.print_exc() # Add traceback for debugging
        return f"Sorry, an error occurred while fetching nutritional information for '{recipe_name}'."
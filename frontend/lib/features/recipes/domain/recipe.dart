/// A saved recipe read from the API. Quantities and totals are for the whole
/// recipe; servings is metadata and does not scale any of these values.
class Recipe {
  const Recipe({
    required this.id,
    required this.createdByUserId,
    required this.title,
    required this.description,
    required this.instructions,
    required this.servings,
    required this.mealType,
    required this.prepTimeMinutes,
    required this.dietType,
    required this.totalCalories,
    required this.totalProteinG,
    required this.totalCarbsG,
    required this.totalFatG,
    required this.createdAt,
    required this.updatedAt,
    required this.ingredients,
  });

  factory Recipe.fromJson(Object? json) {
    final object = _object(json);
    final ingredients = object['recipe_ingredients'];
    if (ingredients is! List) {
      throw const FormatException('Invalid recipe ingredients');
    }
    return Recipe(
      id: _string(object, 'id'),
      createdByUserId: _nullableString(object, 'created_by_user_id'),
      title: _string(object, 'title'),
      description: _nullableString(object, 'description'),
      instructions: _string(object, 'instructions'),
      servings: _integer(object['servings'], 12),
      mealType: _nullableString(object, 'meal_type'),
      prepTimeMinutes: object['prep_time_minutes'] == null
          ? null
          : _integer(object['prep_time_minutes'], 480),
      dietType: _nullableString(object, 'diet_type'),
      totalCalories: _nullableDecimal(object, 'total_calories'),
      totalProteinG: _nullableDecimal(object, 'total_protein_g'),
      totalCarbsG: _nullableDecimal(object, 'total_carbs_g'),
      totalFatG: _nullableDecimal(object, 'total_fat_g'),
      createdAt: _date(object, 'created_at'),
      updatedAt: _date(object, 'updated_at'),
      ingredients: List.unmodifiable(
        ingredients.map(RecipeIngredient.fromJson),
      ),
    );
  }

  final String id;
  final String? createdByUserId;
  final String title;
  final String? description;
  final String instructions;
  final int servings;
  final String? mealType;
  final int? prepTimeMinutes;
  final String? dietType;
  final double? totalCalories;
  final double? totalProteinG;
  final double? totalCarbsG;
  final double? totalFatG;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<RecipeIngredient> ingredients;
}

/// The recipe response contains references and grams, not ingredient names.
class RecipeIngredient {
  const RecipeIngredient({
    required this.id,
    required this.recipeId,
    required this.ingredientId,
    required this.quantityG,
  });

  factory RecipeIngredient.fromJson(Object? json) {
    final object = _object(json);
    final quantity = _decimal(object['quantity_g']);
    if (quantity <= 0) throw const FormatException('Invalid recipe quantity');
    return RecipeIngredient(
      id: _string(object, 'id'),
      recipeId: _string(object, 'recipe_id'),
      ingredientId: _string(object, 'ingredient_id'),
      quantityG: quantity,
    );
  }

  final String id;
  final String recipeId;
  final String ingredientId;
  final double quantityG;
}

Map<String, dynamic> _object(Object? value) {
  if (value is! Map<String, dynamic>) {
    throw const FormatException('Invalid recipe object');
  }
  return value;
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) {
    throw const FormatException('Invalid recipe text');
  }
  return value;
}

String? _nullableString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value == null) return null;
  if (value is! String) throw const FormatException('Invalid recipe text');
  return value;
}

int _integer(Object? value, int maximum) {
  if (value is! int || value < 1 || value > maximum) {
    throw const FormatException('Invalid recipe integer');
  }
  return value;
}

DateTime _date(Map<String, dynamic> json, String key) {
  final parsed = DateTime.tryParse(_string(json, key));
  if (parsed == null) throw const FormatException('Invalid recipe date');
  return parsed;
}

double? _nullableDecimal(Map<String, dynamic> json, String key) =>
    json[key] == null ? null : _decimal(json[key]);

double _decimal(Object? value) {
  if (value is! String) {
    throw const FormatException('Invalid recipe decimal');
  }
  final parsed = double.tryParse(value);
  if (parsed == null || !parsed.isFinite || parsed < 0) {
    throw const FormatException('Invalid recipe decimal');
  }
  return parsed;
}

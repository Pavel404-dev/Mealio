class PantryItem {
  const PantryItem({
    required this.id,
    required this.userId,
    required this.ingredientId,
    required this.quantityG,
    required this.expiresAt,
    required this.createdAt,
    required this.updatedAt,
    required this.ingredient,
  });

  factory PantryItem.fromJson(Object? json) {
    final object = _requiredObject(json, 'PantryItem');

    return PantryItem(
      id: _requiredString(object, 'id'),
      userId: _requiredString(object, 'user_id'),
      ingredientId: _requiredString(object, 'ingredient_id'),
      quantityG: _requiredDecimal(object, 'quantity_g', minimum: 0),
      expiresAt: _nullableDateTime(object, 'expires_at'),
      createdAt: _requiredDateTime(object, 'created_at'),
      updatedAt: _requiredDateTime(object, 'updated_at'),
      ingredient: Ingredient.fromJson(object['ingredient']),
    );
  }

  final String id;
  final String userId;
  final String ingredientId;
  final double quantityG;
  final DateTime? expiresAt;
  final DateTime createdAt;
  final DateTime updatedAt;
  final Ingredient ingredient;

  @override
  bool operator ==(Object other) {
    return other is PantryItem &&
        other.id == id &&
        other.userId == userId &&
        other.ingredientId == ingredientId &&
        other.quantityG == quantityG &&
        other.expiresAt == expiresAt &&
        other.createdAt == createdAt &&
        other.updatedAt == updatedAt &&
        other.ingredient == ingredient;
  }

  @override
  int get hashCode => Object.hash(
    id,
    userId,
    ingredientId,
    quantityG,
    expiresAt,
    createdAt,
    updatedAt,
    ingredient,
  );
}

class Ingredient {
  const Ingredient({
    required this.id,
    required this.name,
    required this.category,
    required this.createdAt,
    required this.nutritionValue,
  });

  factory Ingredient.fromJson(Object? json) {
    final object = _requiredObject(json, 'Ingredient');

    return Ingredient(
      id: _requiredString(object, 'id'),
      name: _requiredString(object, 'name'),
      category: _nullableString(object, 'category'),
      createdAt: _requiredDateTime(object, 'created_at'),
      nutritionValue: object['nutrition_value'] == null
          ? null
          : NutritionValue.fromJson(object['nutrition_value']),
    );
  }

  final String id;
  final String name;
  final String? category;
  final DateTime createdAt;
  final NutritionValue? nutritionValue;

  @override
  bool operator ==(Object other) {
    return other is Ingredient &&
        other.id == id &&
        other.name == name &&
        other.category == category &&
        other.createdAt == createdAt &&
        other.nutritionValue == nutritionValue;
  }

  @override
  int get hashCode =>
      Object.hash(id, name, category, createdAt, nutritionValue);
}

class NutritionValue {
  const NutritionValue({
    required this.id,
    required this.ingredientId,
    required this.calories,
    required this.proteinG,
    required this.carbsG,
    required this.fatG,
    required this.portionG,
  });

  factory NutritionValue.fromJson(Object? json) {
    final object = _requiredObject(json, 'NutritionValue');

    return NutritionValue(
      id: _requiredString(object, 'id'),
      ingredientId: _requiredString(object, 'ingredient_id'),
      calories: _requiredDecimal(object, 'calories', minimum: 0),
      proteinG: _requiredDecimal(object, 'protein_g', minimum: 0),
      carbsG: _requiredDecimal(object, 'carbs_g', minimum: 0),
      fatG: _requiredDecimal(object, 'fat_g', minimum: 0),
      portionG: _requiredDecimal(
        object,
        'portion_g',
        minimum: 0,
        minimumIsExclusive: true,
      ),
    );
  }

  final String id;
  final String ingredientId;
  final double calories;
  final double proteinG;
  final double carbsG;
  final double fatG;
  final double portionG;

  @override
  bool operator ==(Object other) {
    return other is NutritionValue &&
        other.id == id &&
        other.ingredientId == ingredientId &&
        other.calories == calories &&
        other.proteinG == proteinG &&
        other.carbsG == carbsG &&
        other.fatG == fatG &&
        other.portionG == portionG;
  }

  @override
  int get hashCode =>
      Object.hash(id, ingredientId, calories, proteinG, carbsG, fatG, portionG);
}

Map<String, dynamic> _requiredObject(Object? value, String name) {
  if (value is! Map<String, dynamic>) {
    throw FormatException('Expected an object for $name');
  }

  return value;
}

String _requiredString(Map<String, dynamic> json, String key) {
  final value = json[key];

  if (value is! String || value.trim().isEmpty) {
    throw FormatException('Invalid $key');
  }

  return value.trim();
}

String? _nullableString(Map<String, dynamic> json, String key) {
  final value = json[key];

  if (value == null) {
    return null;
  }

  if (value is! String) {
    throw FormatException('Invalid $key');
  }

  return value;
}

DateTime _requiredDateTime(Map<String, dynamic> json, String key) {
  final value = _requiredString(json, key);
  final parsedValue = DateTime.tryParse(value);

  if (parsedValue == null) {
    throw FormatException('Invalid $key');
  }

  return parsedValue;
}

DateTime? _nullableDateTime(Map<String, dynamic> json, String key) {
  final value = json[key];

  if (value == null) {
    return null;
  }

  if (value is! String || value.trim().isEmpty) {
    throw FormatException('Invalid $key');
  }

  final parsedValue = DateTime.tryParse(value);
  if (parsedValue == null) {
    throw FormatException('Invalid $key');
  }

  return parsedValue;
}

double _requiredDecimal(
  Map<String, dynamic> json,
  String key, {
  required double minimum,
  bool minimumIsExclusive = false,
}) {
  final value = json[key];

  if (value is! String || value.trim().isEmpty) {
    throw FormatException('Invalid $key');
  }

  final parsedValue = double.tryParse(value);
  final isBelowMinimum = minimumIsExclusive
      ? parsedValue != null && parsedValue <= minimum
      : parsedValue != null && parsedValue < minimum;

  if (parsedValue == null || !parsedValue.isFinite || isBelowMinimum) {
    throw FormatException('Invalid $key');
  }

  return parsedValue;
}

import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/pantry/domain/pantry_item.dart';

void main() {
  const fullItemJson = {
    'id': 'pantry-1',
    'user_id': 'user-1',
    'ingredient_id': 'ingredient-1',
    'quantity_g': '250.50',
    'expires_at': '2026-09-30T10:00:00Z',
    'created_at': '2026-09-10T10:00:00Z',
    'updated_at': '2026-09-11T10:00:00Z',
    'ingredient': {
      'id': 'ingredient-1',
      'name': 'Oats',
      'category': 'grain',
      'created_at': '2026-09-01T10:00:00Z',
      'nutrition_value': {
        'id': 'nutrition-1',
        'ingredient_id': 'ingredient-1',
        'calories': '389.00',
        'protein_g': '16.90',
        'carbs_g': '66.30',
        'fat_g': '6.90',
        'portion_g': '100.00',
      },
    },
  };

  Map<String, dynamic> itemJson() {
    final ingredient = Map<String, dynamic>.from(
      fullItemJson['ingredient']! as Map,
    );
    ingredient['nutrition_value'] = Map<String, dynamic>.from(
      ingredient['nutrition_value']! as Map,
    );
    return Map<String, dynamic>.from(fullItemJson)..['ingredient'] = ingredient;
  }

  test('parses a full pantry item', () {
    final item = PantryItem.fromJson(fullItemJson);

    expect(item.id, 'pantry-1');
    expect(item.quantityG, 250.5);
    expect(item.expiresAt, DateTime.parse('2026-09-30T10:00:00Z'));
    expect(item.ingredient.name, 'Oats');
    expect(item.ingredient.category, 'grain');
    expect(item.ingredient.nutritionValue?.calories, 389);
    expect(item.ingredient.nutritionValue?.portionG, 100);
  });

  test('accepts nullable expiry, category, and nutrition', () {
    final json = itemJson();
    json['expires_at'] = null;
    final ingredient = json['ingredient']! as Map<String, dynamic>;
    ingredient['category'] = null;
    ingredient['nutrition_value'] = null;

    final item = PantryItem.fromJson(json);

    expect(item.expiresAt, isNull);
    expect(item.ingredient.category, isNull);
    expect(item.ingredient.nutritionValue, isNull);
  });

  test('rejects a malformed root item', () {
    expect(() => PantryItem.fromJson(['not-an-object']), throwsFormatException);
  });

  test('rejects a missing required field', () {
    final json = itemJson()..remove('id');

    expect(() => PantryItem.fromJson(json), throwsFormatException);
  });

  test('rejects invalid required and nullable timestamps', () {
    final invalidCreatedAt = itemJson()..['created_at'] = 'not-a-date';
    final invalidExpiry = itemJson()..['expires_at'] = 'not-a-date';

    expect(() => PantryItem.fromJson(invalidCreatedAt), throwsFormatException);
    expect(() => PantryItem.fromJson(invalidExpiry), throwsFormatException);
  });

  test('rejects a malformed ingredient and empty ingredient name', () {
    final malformedIngredient = itemJson()..['ingredient'] = [];
    final emptyName = itemJson();
    (emptyName['ingredient']! as Map<String, dynamic>)['name'] = '   ';

    expect(
      () => PantryItem.fromJson(malformedIngredient),
      throwsFormatException,
    );
    expect(() => PantryItem.fromJson(emptyName), throwsFormatException);
  });

  test('rejects malformed nutrition', () {
    final json = itemJson();
    (json['ingredient']! as Map<String, dynamic>)['nutrition_value'] = [];

    expect(() => PantryItem.fromJson(json), throwsFormatException);
  });

  test('rejects non-string, empty, and invalid decimals', () {
    for (final value in <Object>['', 'invalid', 250]) {
      final json = itemJson()..['quantity_g'] = value;
      expect(() => PantryItem.fromJson(json), throwsFormatException);
    }
  });

  test('rejects negative nutrition values', () {
    final json = itemJson();
    final nutrition =
        (json['ingredient']! as Map<String, dynamic>)['nutrition_value']!
            as Map<String, dynamic>;
    nutrition['calories'] = '-1';

    expect(() => PantryItem.fromJson(json), throwsFormatException);
  });

  test('rejects zero and negative portions', () {
    for (final value in ['0', '-1']) {
      final json = itemJson();
      final nutrition =
          (json['ingredient']! as Map<String, dynamic>)['nutrition_value']!
              as Map<String, dynamic>;
      nutrition['portion_g'] = value;
      expect(() => PantryItem.fromJson(json), throwsFormatException);
    }
  });

  test('accepts zero quantity', () {
    final item = PantryItem.fromJson(itemJson()..['quantity_g'] = '0');

    expect(item.quantityG, 0);
  });

  test('rejects NaN and Infinity decimals', () {
    for (final value in ['NaN', 'Infinity', '-Infinity']) {
      final json = itemJson()..['quantity_g'] = value;
      expect(() => PantryItem.fromJson(json), throwsFormatException);
    }
  });
}

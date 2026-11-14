import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/recipes/domain/recipe.dart';

import '../../../helpers/recipe_test_fakes.dart';

void main() {
  test(
    'reads saved quantities and whole-recipe totals independently of servings',
    () {
      final recipe = Recipe.fromJson(recipeJson());
      expect(recipe.id, 'recipe-1');
      expect(recipe.createdByUserId, 'owner-1');
      expect(recipe.title, 'Saved recipe');
      expect(recipe.description, 'A saved recipe description');
      expect(recipe.instructions, 'First step.\nSecond step.');
      expect(recipe.servings, 4);
      expect(recipe.mealType, 'brunch');
      expect(recipe.prepTimeMinutes, 30);
      expect(recipe.totalCalories, 330);
      expect(recipe.totalProteinG, 62);
      expect(recipe.totalCarbsG, 0);
      expect(recipe.totalFatG, 7.2);
      expect(recipe.createdAt, DateTime.utc(2026, 11, 14, 10));
      expect(recipe.updatedAt, recipe.createdAt);
      final ingredient = recipe.ingredients.single;
      expect(ingredient.id, 'composition-1');
      expect(ingredient.recipeId, recipe.id);
      expect(ingredient.ingredientId, 'ingredient-1');
      expect(ingredient.quantityG, 200);
      expect(() => recipe.ingredients.clear(), throwsUnsupportedError);
    },
  );

  test('nullable values stay missing, explicit zero stays numeric zero', () {
    final json = recipeJson();
    for (final field in [
      'created_by_user_id',
      'description',
      'meal_type',
      'prep_time_minutes',
      'diet_type',
      'total_calories',
      'total_protein_g',
      'total_fat_g',
    ]) {
      json[field] = null;
    }
    json['recipe_ingredients'] = [];
    final recipe = Recipe.fromJson(json);
    expect(recipe.createdByUserId, isNull);
    expect(recipe.description, isNull);
    expect(recipe.mealType, isNull);
    expect(recipe.prepTimeMinutes, isNull);
    expect(recipe.dietType, isNull);
    expect(recipe.totalCalories, isNull);
    expect(recipe.totalProteinG, isNull);
    expect(recipe.totalFatG, isNull);
    expect(recipe.totalCarbsG, 0);
    expect(recipe.ingredients, isEmpty);
  });

  test(
    'nullable defaulted fields may be omitted and additive fields ignored',
    () {
      final json = recipeJson()
        ..remove('meal_type')
        ..remove('prep_time_minutes')
        ..remove('total_calories')
        ..['future_field'] = {'value': 'additive'};
      final recipe = Recipe.fromJson(json);
      expect(recipe.mealType, isNull);
      expect(recipe.prepTimeMinutes, isNull);
      expect(recipe.totalCalories, isNull);
    },
  );

  test('preserves long Unicode title, instructions and custom metadata', () {
    final title = List.filled(255, 'Я').join();
    final instructions = List.filled(500, 'Шаг {one}\n').join();
    final recipe = Recipe.fromJson(
      recipeJson(title: title)
        ..['instructions'] = instructions
        ..['meal_type'] = 'второй завтрак',
    );
    expect(recipe.title, title);
    expect(recipe.instructions, instructions);
    expect(recipe.mealType, 'второй завтрак');
  });

  for (final count in [1, 12]) {
    test('accepts servings boundary $count', () {
      expect(
        Recipe.fromJson(recipeJson()..['servings'] = count).servings,
        count,
      );
    });
  }
  for (final value in [null, true, '4', 4.0, 0, 13]) {
    test('rejects invalid required servings $value (${value.runtimeType})', () {
      expect(
        () => Recipe.fromJson(recipeJson()..['servings'] = value),
        throwsFormatException,
      );
    });
  }
  for (final value in [true, '30', 30.0, 0, 481]) {
    test(
      'rejects invalid preparation duration $value (${value.runtimeType})',
      () {
        expect(
          () => Recipe.fromJson(recipeJson()..['prep_time_minutes'] = value),
          throwsFormatException,
        );
      },
    );
  }
  for (final field in [
    'id',
    'title',
    'instructions',
    'created_at',
    'updated_at',
  ]) {
    test('rejects missing/malformed required $field', () {
      for (final value in [null, '', '   ', true]) {
        expect(
          () => Recipe.fromJson(recipeJson()..[field] = value),
          throwsFormatException,
        );
      }
    });
  }
  for (final field in [
    'total_calories',
    'total_protein_g',
    'total_carbs_g',
    'total_fat_g',
  ]) {
    test('rejects malformed $field instead of silently returning zero', () {
      for (final value in [
        1,
        true,
        '',
        'invalid',
        '-0.01',
        'NaN',
        'Infinity',
        '1e999',
      ]) {
        expect(
          () => Recipe.fromJson(recipeJson()..[field] = value),
          throwsFormatException,
        );
      }
    });
  }
  test('accepts decimal string totals at the persisted upper bound', () {
    expect(
      Recipe.fromJson(
        recipeJson()..['total_calories'] = '99999999.99',
      ).totalCalories,
      99999999.99,
    );
  });

  test('rejects malformed roots, dates, optional text and composition', () {
    for (final root in [null, [], 'recipe']) {
      expect(() => Recipe.fromJson(root), throwsFormatException);
    }
    for (final field in ['created_at', 'updated_at']) {
      expect(
        () => Recipe.fromJson(recipeJson()..[field] = 'not-a-date'),
        throwsFormatException,
      );
    }
    for (final field in [
      'description',
      'created_by_user_id',
      'meal_type',
      'diet_type',
    ]) {
      expect(
        () => Recipe.fromJson(recipeJson()..[field] = 42),
        throwsFormatException,
      );
    }
    for (final value in [
      null,
      {},
      [null],
      [
        {'quantity_g': '10.00'},
      ],
    ]) {
      expect(
        () => Recipe.fromJson(recipeJson()..['recipe_ingredients'] = value),
        throwsFormatException,
      );
    }
    for (final value in [
      null,
      2,
      true,
      '',
      '0.00',
      '-1.00',
      'NaN',
      'Infinity',
    ]) {
      final json = recipeJson();
      (json['recipe_ingredients'] as List).single['quantity_g'] = value;
      expect(() => Recipe.fromJson(json), throwsFormatException);
    }
  });
}

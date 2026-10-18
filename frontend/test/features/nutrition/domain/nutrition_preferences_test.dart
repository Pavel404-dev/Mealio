import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/nutrition/domain/nutrition_preferences.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';
import 'package:mealio/features/nutrition/domain/nutrition_calculation.dart';
import '../../../helpers/nutrition_test_fakes.dart';

void main() {
  test(
    'typed read retains custom diet/currency, partial targets and unrestricted lists',
    () {
      final values = List.generate(30, (i) => '${'x' * 101} $i');
      final json = nutritionJson()
        ..addAll({
          'diet_type': 'custom diet',
          'budget_currency': 'ZZZ',
          'liked_ingredients': values,
          'allergies': ['peanuts', 'peanuts'],
          'disliked_ingredients': ['peanuts'],
        });
      final profile = NutritionProfile.fromJson(json);
      expect(profile.preferences.likes, values);
      expect(profile.preferences.diet, 'custom diet');
      expect(profile.preferences.budget!.currency, 'ZZZ');
      expect(profile.preferences.allergies, ['peanuts', 'peanuts']);
      expect(profile.targets.any, isTrue);
      expect(profile.targets.complete, isFalse);
      expect(profile.targets.carbs, isNull);
      expect(() => profile.preferences.likes.clear(), throwsUnsupportedError);
    },
  );
  test('old backend missing likes and malformed typed fields fail safely', () {
    expect(
      () => NutritionProfile.fromJson(
        nutritionJson()..remove('liked_ingredients'),
      ),
      throwsFormatException,
    );
    for (final patch in [
      {'liked_ingredients': null},
      {
        'liked_ingredients': [1],
      },
      {'max_cooking_time_minutes': 1.0},
      {'max_cooking_time_minutes': '45'},
      {'weekly_food_budget_amount': 50.12},
      {'weekly_food_budget_amount': '50.125'},
      {'budget_currency': null},
      {'daily_calories_target': 1.5},
    ]) {
      expect(
        () => NutritionProfile.fromJson(nutritionJson()..addAll(patch)),
        throwsFormatException,
      );
    }
  });
  test(
    'food PATCH distinguishes omit/clear; preserves duplicates and intersections',
    () {
      expect(NutritionPatch.food().json, isEmpty);
      expect(NutritionPatch.food(diet: const NutritionChange(null)).json, {
        'diet_type': null,
      });
      expect(NutritionPatch.food(likes: const NutritionChange([])).json, {
        'liked_ingredients': [],
      });
      expect(
        NutritionPatch.food(
          likes: const NutritionChange([' peanuts ', '', 'peanuts']),
          dislikes: const NutritionChange(['peanuts']),
        ).json,
        {
          'liked_ingredients': ['peanuts', 'peanuts'],
          'disliked_ingredients': ['peanuts'],
        },
      );
    },
  );
  test(
    'exact budget comma/point, paired clearing and strict cooking integer',
    () {
      expect(
        NutritionPatch.practical(
          budget: const NutritionChange(NutritionBudget('50,12', ' eur ')),
        ).json,
        {'weekly_food_budget_amount': '50.12', 'budget_currency': 'EUR'},
      );
      expect(
        NutritionPatch.practical(budget: const NutritionChange(null)).json,
        {'weekly_food_budget_amount': null, 'budget_currency': null},
      );
      expect(
        NutritionPatch.practical(cookingTime: const NutritionChange(45)).json,
        {'max_cooking_time_minutes': 45},
      );
      expect(
        NutritionPatch.practical(cookingTime: const NutritionChange(null)).json,
        {'max_cooking_time_minutes': null},
      );
      for (final value in [
        '50,125',
        '50.120',
        '0',
        '1000000.01',
        'NaN',
        '1e2',
      ]) {
        expect(
          preferenceError(PreferenceField.budgetAmount, value),
          PreferenceError.budgetAmount,
        );
      }
      for (final value in ['0.01', '1000000.00', '50,12']) {
        expect(preferenceError(PreferenceField.budgetAmount, value), isNull);
      }
      for (final value in ['1.0', '0', '481']) {
        expect(
          preferenceError(PreferenceField.cookingTime, value),
          PreferenceError.cookingTime,
        );
      }
    },
  );
  test('calculated snapshot and targets-only exact integer serializer', () {
    final outcome =
        NutritionCalculation.fromJson(calculationJson(), date: '2026-10-04')
            as NutritionCalculated;
    expect(outcome.usedInputs[NutritionField.height], '180.0');
    expect(NutritionPatch.targets(outcome.targets).json, {
      'daily_calories_target': 3204,
      'daily_protein_target_g': 160,
      'daily_carbs_target_g': 400,
      'daily_fat_target_g': 107,
    });
    expect(
      nutritionCalculationDate(DateTime.parse('2026-10-05T00:30:00+02:00')),
      '2026-10-04',
    );
  });
  test(
    'incomplete/unsupported are typed, unknown or malformed outcomes fail',
    () {
      final base = {
        'rules_version': 'mealio-nutrition-v1',
        'calculation_date': '2026-10-04',
        'result': null,
      };
      expect(
        NutritionCalculation.fromJson({
          ...base,
          'status': 'incomplete_profile',
          'missing_fields': ['sex'],
        }, date: '2026-10-04'),
        isA<NutritionIncomplete>(),
      );
      for (final reason in NutritionUnsupportedReason.values) {
        final result =
            NutritionCalculation.fromJson({
                  ...base,
                  'status': 'unsupported_profile',
                  'reason_codes': [reason.wireName],
                }, date: '2026-10-04')
                as NutritionUnsupported;
        expect(result.reasons, [reason]);
      }
      for (final json in [
        {...base, 'status': 'unknown'},
        {...base, 'status': 'calculated'},
        {
          ...base,
          'status': 'unsupported_profile',
          'reason_codes': ['unknown'],
        },
        {...base, 'status': 'incomplete_profile', 'missing_fields': []},
        calculationJson()..['rules_version'] = 'future',
        calculationJson()..['calculation_date'] = '2026-10-05',
      ]) {
        expect(
          () => NutritionCalculation.fromJson(json, date: '2026-10-04'),
          throwsA(anything),
        );
      }
    },
  );
}

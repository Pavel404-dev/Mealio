import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/nutrition/domain/nutrition_calculation.dart';

import '../../../helpers/nutrition_test_fakes.dart';

void main() {
  for (final entry in invalidCalculationResults.entries) {
    test('calculated rejects ${entry.key}', () {
      expect(
        () => NutritionCalculation.fromJson(
          calculationJson(resultOverrides: entry.value),
          date: '2026-10-04',
        ),
        throwsFormatException,
      );
    });
  }
  // These macros supply 3203 kcal. Check both inclusive discrepancy edges
  // and each allowed signed delta without reproducing the backend formula.
  for (final entry in {-2: 3205, -1: 3204, 0: 3203, 1: 3202, 2: 3201}.entries) {
    test('calculated accepts exact delta ${entry.key}', () {
      final result =
          NutritionCalculation.fromJson(
                calculationJson(
                  resultOverrides: {
                    'calories_target_kcal': entry.value,
                    'energy_delta_kcal': entry.key,
                  },
                ),
                date: '2026-10-04',
              )
              as NutritionCalculated;
      expect(result.targets.calories, entry.value);
      expect(result.targets.protein, 160);
      expect(result.targets.carbs, 400);
      expect(result.targets.fat, 107);
    });
  }
  for (final age in [19, 78]) {
    test('calculated accepts age boundary $age', () {
      expect(
        NutritionCalculation.fromJson(
          calculationJson(resultOverrides: {'age_years': age}),
          date: '2026-10-04',
        ),
        isA<NutritionCalculated>(),
      );
    });
  }
  test('positive decimal metadata needs no floating-point conversion', () {
    expect(
      NutritionCalculation.fromJson(
        calculationJson(
          resultOverrides: {
            'activity_factor': '0.${'0' * 400}1',
            'goal_factor': '000.0100',
            'ree_kcal': '1',
            'tdee_kcal': '1${'0' * 400}.00',
          },
        ),
        date: '2026-10-04',
      ),
      isA<NutritionCalculated>(),
    );
  });
}

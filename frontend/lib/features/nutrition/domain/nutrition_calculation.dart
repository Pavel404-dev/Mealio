import 'nutrition_preferences.dart';
import 'nutrition_profile.dart';

enum NutritionUnsupportedReason {
  birthDateAfterCalculationDate('birth_date_after_calculation_date'),
  age('age_out_of_range'),
  height('height_out_of_range'),
  weight('weight_out_of_range'),
  bmi('bmi_out_of_range'),
  energy('nonpositive_energy'),
  calories('calories_out_of_range');

  const NutritionUnsupportedReason(this.wireName);
  final String wireName;
}

sealed class NutritionCalculation {
  const NutritionCalculation(this.date);
  static const rulesVersion = 'mealio-nutrition-v1';
  final String date;

  factory NutritionCalculation.fromJson(Object? data, {required String date}) {
    if (data is! Map<String, dynamic> ||
        data['calculation_date'] != date ||
        data['rules_version'] != rulesVersion) {
      throw const FormatException('Invalid calculation');
    }
    switch (data['status']) {
      case 'calculated':
        final result = data['result'];
        if (result is! Map<String, dynamic> ||
            result['used_inputs'] is! Map<String, dynamic>) {
          throw const FormatException('Invalid calculation result');
        }
        final used = result['used_inputs'] as Map<String, dynamic>;
        final inputs = <NutritionField, String>{};
        for (final field in NutritionField.values) {
          final value = used[field.wireName];
          if (value is! String ||
              value.contains(',') ||
              nutritionInputError(field, value) != null) {
            throw const FormatException('Invalid used inputs');
          }
          inputs[field] = value;
        }
        for (final key in [
          'activity_factor',
          'goal_factor',
          'ree_kcal',
          'tdee_kcal',
        ]) {
          final value = result[key];
          if (value is! String ||
              !RegExp(r'^[0-9]+(?:\.[0-9]+)?$').hasMatch(value)) {
            throw const FormatException('Invalid calculation metadata');
          }
        }
        if (result['age_years'] is! int ||
            result['energy_delta_kcal'] is! int) {
          throw const FormatException('Invalid calculation metadata');
        }
        final targets = NutritionTargets.fromJson({
          'daily_calories_target': result['calories_target_kcal'],
          'daily_protein_target_g': result['protein_target_g'],
          'daily_carbs_target_g': result['carbs_target_g'],
          'daily_fat_target_g': result['fat_target_g'],
        });
        if (!targets.complete) {
          throw const FormatException('Incomplete estimate');
        }
        return NutritionCalculated(date, targets, inputs);
      case 'incomplete_profile':
        final fields = data['missing_fields'];
        if (data['result'] != null ||
            !data.containsKey('result') ||
            fields is! List ||
            fields.isEmpty) {
          throw const FormatException('Invalid missing fields');
        }
        return NutritionIncomplete(date, [
          for (final field in fields)
            NutritionField.values.firstWhere((f) => f.wireName == field),
        ]);
      case 'unsupported_profile':
        final reasons = data['reason_codes'];
        if (data['result'] != null ||
            !data.containsKey('result') ||
            reasons is! List ||
            reasons.isEmpty) {
          throw const FormatException('Invalid reasons');
        }
        return NutritionUnsupported(date, [
          for (final reason in reasons)
            NutritionUnsupportedReason.values.firstWhere(
              (r) => r.wireName == reason,
            ),
        ]);
      default:
        throw const FormatException('Unknown calculation outcome');
    }
  }
}

class NutritionCalculated extends NutritionCalculation {
  NutritionCalculated(
    super.date,
    this.targets,
    Map<NutritionField, String> inputs,
  ) : usedInputs = Map.unmodifiable(inputs);
  final NutritionTargets targets;
  final Map<NutritionField, String> usedInputs;
}

class NutritionIncomplete extends NutritionCalculation {
  NutritionIncomplete(super.date, List<NutritionField> fields)
    : missing = List.unmodifiable(fields);
  final List<NutritionField> missing;
}

class NutritionUnsupported extends NutritionCalculation {
  NutritionUnsupported(super.date, List<NutritionUnsupportedReason> reasons)
    : reasons = List.unmodifiable(reasons);
  final List<NutritionUnsupportedReason> reasons;
}

String nutritionCalculationDate(DateTime time) {
  final utc = time.toUtc();
  return '${utc.year.toString().padLeft(4, '0')}-${utc.month.toString().padLeft(2, '0')}-${utc.day.toString().padLeft(2, '0')}';
}

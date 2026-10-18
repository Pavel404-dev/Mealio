import 'nutrition_preferences.dart';

enum NutritionField {
  goal('goal', 0),
  sex('sex', 1),
  birthDate('birth_date', 1),
  height('height_cm', 1),
  weight('weight_kg', 1),
  activity('activity_level', 2);

  const NutritionField(this.wireName, this.step);
  final String wireName;
  final int step;

  List<String> get choices => switch (this) {
    goal => const ['lose_weight', 'maintain', 'gain_weight'],
    sex => const ['male', 'female'],
    activity => const [
      'sedentary',
      'lightly_active',
      'moderately_active',
      'very_active',
      'extra_active',
    ],
    _ => const [],
  };
}

enum NutritionInputError { required, choice, birthDate, height, weight }

/// Formula inputs plus typed canonical preferences and saved targets.
class NutritionProfile {
  NutritionProfile._(
    Map<NutritionField, String?> values,
    this.preferences,
    this.targets,
  ) : values = Map.unmodifiable(values);

  final Map<NutritionField, String?> values;
  final NutritionPreferences preferences;
  final NutritionTargets targets;

  factory NutritionProfile.fromJson(Object? json, {DateTime? now}) {
    if (json is! Map<String, dynamic>) {
      throw const FormatException('Invalid nutrition response');
    }
    final values = <NutritionField, String?>{};
    for (final field in NutritionField.values) {
      // The canonical API always includes nullable fields. Missing keys are a
      // malformed response, not evidence that a saved measurement was cleared.
      if (!json.containsKey(field.wireName)) {
        throw const FormatException('Incomplete nutrition response');
      }
      final value = json[field.wireName];
      if (value == null && field != NutritionField.goal) {
        values[field] = null;
      } else if (value is String &&
          !value.contains(',') &&
          value == value.trim() &&
          nutritionInputError(field, value, now: now) == null) {
        values[field] = value;
      } else {
        throw const FormatException('Invalid nutrition field');
      }
    }
    return NutritionProfile._(
      values,
      NutritionPreferences.fromJson(json),
      NutritionTargets.fromJson(json),
    );
  }
}

NutritionInputError? nutritionInputError(
  NutritionField field,
  String input, {
  DateTime? now,
}) {
  final value = input.trim();
  if (value.isEmpty) return NutritionInputError.required;
  if (field.choices.isNotEmpty) {
    return field.choices.contains(value) ? null : NutritionInputError.choice;
  }
  if (field == NutritionField.birthDate) {
    if (!RegExp(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$').hasMatch(value)) {
      return NutritionInputError.birthDate;
    }
    final year = int.parse(value.substring(0, 4));
    final month = int.parse(value.substring(5, 7));
    final day = int.parse(value.substring(8, 10));
    final date = DateTime.utc(year, month, day);
    final utc = (now ?? DateTime.now()).toUtc();
    final today = DateTime.utc(utc.year, utc.month, utc.day);
    return year >= 1900 &&
            date.year == year &&
            date.month == month &&
            date.day == day &&
            !date.isAfter(today)
        ? null
        : NutritionInputError.birthDate;
  }
  final height = field == NutritionField.height;
  final scale = height ? 1 : 2;
  final pattern = RegExp('^[0-9]{1,3}(?:[.,][0-9]{1,$scale})?\$');
  final error = height
      ? NutritionInputError.height
      : NutritionInputError.weight;
  if (!pattern.hasMatch(value)) return error;
  final scaled = _scaledDecimal(value, scale);
  final min = height ? 500 : 1000;
  final max = height ? 2500 : 50000;
  return scaled >= min && scaled <= max ? null : error;
}

String nutritionWireValue(String input) => input.trim().replaceAll(',', '.');

bool nutritionValuesEqual(NutritionField field, String input, String? saved) {
  if (saved == null) return input.isEmpty;
  if (field == NutritionField.height || field == NutritionField.weight) {
    // Validate scale before comparison: 170.00 must not become a no-op height.
    if (nutritionInputError(field, input) != null) return false;
    final scale = field == NutritionField.height ? 1 : 2;
    return _scaledDecimal(input.trim(), scale) == _scaledDecimal(saved, scale);
  }
  return input == saved;
}

int _scaledDecimal(String value, int scale) {
  final parts = value.replaceAll(',', '.').split('.');
  return int.parse(
    '${parts.first}${(parts.length == 2 ? parts[1] : '').padRight(scale, '0')}',
  );
}

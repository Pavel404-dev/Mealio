import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';

import '../../../helpers/nutrition_test_fakes.dart';

void main() {
  test(
    'canonical partial and full response; unrelated values are not writable',
    () {
      final partial = NutritionProfile.fromJson(nutritionJson());
      expect(partial.values[NutritionField.goal], 'maintain');
      expect(partial.values[NutritionField.activity], isNull);
      final full = NutritionProfile.fromJson(nutritionJson(full: true));
      expect(full.values.length, 6);
      expect(full.values[NutritionField.birthDate], '1992-02-29');
      expect(full.values[NutritionField.height], '170.0');
      expect(full.values[NutritionField.weight], '70.25');
      expect(() => full.values.clear(), throwsUnsupportedError);
    },
  );

  for (final field in NutritionField.values) {
    test('${field.wireName}: missing is malformed; nullable is explicit', () {
      final json = nutritionJson()..remove(field.wireName);
      expect(() => NutritionProfile.fromJson(json), throwsFormatException);
      json[field.wireName] = null;
      if (field == NutritionField.goal) {
        expect(() => NutritionProfile.fromJson(json), throwsFormatException);
      } else {
        expect(NutritionProfile.fromJson(json).values[field], isNull);
      }
    });
    for (final choice in field.choices) {
      test('${field.wireName}: accepts $choice', () {
        final json = nutritionJson()..[field.wireName] = choice;
        expect(NutritionProfile.fromJson(json).values[field], choice);
      });
    }
    for (final invalid in [true, 1, [], {}, 'unknown']) {
      test('${field.wireName}: rejects invalid type/value $invalid', () {
        final json = nutritionJson()..[field.wireName] = invalid;
        expect(() => NutritionProfile.fromJson(json), throwsFormatException);
      });
    }
  }

  for (final field in [NutritionField.height, NutritionField.weight]) {
    final height = field == NutritionField.height;
    final valid = height
        ? ['50', '50.0', '250.0', '193,0', '193.0']
        : ['10', '10.00', '500.00', '78,40', '78.40'];
    for (final value in valid) {
      test('${field.wireName}: exact accepted $value', () {
        expect(nutritionInputError(field, value), isNull);
        expect(nutritionWireValue(value), value.replaceAll(',', '.'));
      });
    }
    final invalid = height
        ? ['49.9', '250.1', '193.00', '170.01']
        : ['9.99', '500.01', '78.400', '70.001'];
    for (final value in [
      ...invalid,
      'NaN',
      'Infinity',
      '-1',
      '1e2',
      '1,2.3',
      '.5',
      '1000',
      '1.',
      '１２３',
    ]) {
      test('${field.wireName}: rejects $value without rounding', () {
        expect(nutritionInputError(field, value), isNotNull);
      });
    }
    test(
      '${field.wireName}: missing required and numeric response rejected',
      () {
        expect(nutritionInputError(field, ' '), NutritionInputError.required);
        expect(
          () => NutritionProfile.fromJson(
            nutritionJson()..[field.wireName] = 100.0,
          ),
          throwsFormatException,
        );
      },
    );
  }

  test(
    'decimal equality preserves scale validation and exact wire strings',
    () {
      expect(
        nutritionValuesEqual(NutritionField.weight, '078,40', '78.4'),
        isTrue,
      );
      expect(
        nutritionValuesEqual(NutritionField.height, '170.00', '170.0'),
        isFalse,
      );
      expect(nutritionWireValue(' 78,40 '), '78.40');
    },
  );

  for (final value in ['1900-01-01', '2000-02-29', '2026-10-17']) {
    test('date accepts actual calendar day $value inclusive UTC bounds', () {
      expect(
        nutritionInputError(
          NutritionField.birthDate,
          value,
          now: DateTime.utc(2026, 10, 17),
        ),
        isNull,
      );
    });
  }
  for (final value in [
    '1899-12-31',
    '1900-02-29',
    '2025-02-29',
    '2026-13-01',
    '2026-02-30',
    '2026-00-01',
    '2026-01-00',
    '2026-10-18',
    '2026-1-01',
    '2000-01-01T00:00:00Z',
    '30',
  ]) {
    test('date rejects $value without normalization', () {
      expect(
        nutritionInputError(
          NutritionField.birthDate,
          value,
          now: DateTime.utc(2026, 10, 17),
        ),
        NutritionInputError.birthDate,
      );
    });
  }
  test(
    'today uses UTC, never the input timezone or a synthesized birthday',
    () {
      final instant = DateTime.parse('2026-10-18T00:30:00+02:00');
      expect(
        nutritionInputError(
          NutritionField.birthDate,
          '2026-10-17',
          now: instant,
        ),
        isNull,
      );
      expect(
        nutritionInputError(
          NutritionField.birthDate,
          '2026-10-18',
          now: instant,
        ),
        NutritionInputError.birthDate,
      );
    },
  );
  test('W4 bounds stay wider than W5 applicability', () {
    final json = nutritionJson(full: true)
      ..['birth_date'] = '1900-01-01'
      ..['height_cm'] = '50.0'
      ..['weight_kg'] = '500.00';
    expect(
      NutritionProfile.fromJson(json).values[NutritionField.weight],
      '500.00',
    );
  });
}

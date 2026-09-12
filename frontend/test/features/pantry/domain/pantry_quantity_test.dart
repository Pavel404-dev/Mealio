import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/pantry/domain/pantry_quantity.dart';

void main() {
  test('normalizes a comma without using floating point', () {
    expect(PantryQuantity.fromInput(' 500,25 ').value, '500.25');
  });

  test('accepts the database maximum and ordinary positive values', () {
    for (final value in ['0.01', '1', '500.25', '99999999.99']) {
      expect(PantryQuantity.validate(value), isNull);
    }
  });

  test('rejects invalid decimal representations', () {
    for (final value in [
      '',
      '   ',
      '0',
      '0.00',
      '-1',
      'word',
      '1.2.3',
      '1e2',
      'NaN',
      'Infinity',
      '1.234',
      '100000000',
      '.5',
    ]) {
      expect(PantryQuantity.validate(value), isNotNull, reason: value);
      expect(
        () => PantryQuantity.fromInput(value),
        throwsFormatException,
        reason: value,
      );
    }
  });
}

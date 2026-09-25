enum PantryQuantityError { required, invalid, nonPositive }

class PantryQuantity {
  const PantryQuantity._(this.value);

  static final RegExp _pattern = RegExp(r'^\d{1,8}(?:[.,]\d{1,2})?$');

  final String value;

  static String? validate(String? input) => switch (validationError(input)) {
    null => null,
    PantryQuantityError.required => 'Quantity is required.',
    PantryQuantityError.invalid => 'Enter up to 8 digits and 2 decimal places.',
    PantryQuantityError.nonPositive => 'Quantity must be greater than zero.',
  };

  static PantryQuantityError? validationError(String? input) {
    final value = input?.trim() ?? '';
    if (value.isEmpty) {
      return PantryQuantityError.required;
    }
    if (!_pattern.hasMatch(value)) {
      return PantryQuantityError.invalid;
    }

    final digits = value.replaceAll(RegExp(r'[.,]'), '');
    if (digits.runes.every((digit) => digit == 48)) {
      return PantryQuantityError.nonPositive;
    }
    return null;
  }

  factory PantryQuantity.fromInput(String input) {
    final error = validate(input);
    if (error != null) {
      throw FormatException(error);
    }
    return PantryQuantity._(input.trim().replaceAll(',', '.'));
  }
}

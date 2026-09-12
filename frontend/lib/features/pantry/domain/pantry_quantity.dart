class PantryQuantity {
  const PantryQuantity._(this.value);

  static final RegExp _pattern = RegExp(r'^\d{1,8}(?:[.,]\d{1,2})?$');

  final String value;

  static String? validate(String? input) {
    final value = input?.trim() ?? '';
    if (value.isEmpty) {
      return 'Quantity is required.';
    }
    if (!_pattern.hasMatch(value)) {
      return 'Enter up to 8 digits and 2 decimal places.';
    }

    final digits = value.replaceAll(RegExp(r'[.,]'), '');
    if (digits.runes.every((digit) => digit == 48)) {
      return 'Quantity must be greater than zero.';
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

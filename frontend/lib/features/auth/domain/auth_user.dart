class AuthUser {
  const AuthUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.createdAt,
    required this.updatedAt,
  });

  factory AuthUser.fromJson(Object? json) {
    if (json is! Map<String, dynamic>) {
      throw const FormatException('Expected an object for AuthUser');
    }

    return AuthUser(
      id: _requiredString(json, 'id'),
      email: _requiredString(json, 'email'),
      fullName: _nullableString(json, 'full_name'),
      createdAt: _requiredDateTime(json, 'created_at'),
      updatedAt: _requiredDateTime(json, 'updated_at'),
    );
  }

  final String id;
  final String email;
  final String? fullName;
  final DateTime createdAt;
  final DateTime updatedAt;

  static String _requiredString(Map<String, dynamic> json, String key) {
    final value = json[key];

    if (value is! String || value.trim().isEmpty) {
      throw FormatException('Invalid $key');
    }

    return value.trim();
  }

  static String? _nullableString(Map<String, dynamic> json, String key) {
    final value = json[key];

    if (value == null) {
      return null;
    }

    if (value is! String) {
      throw FormatException('Invalid $key');
    }

    final normalizedValue = value.trim();
    return normalizedValue.isEmpty ? null : normalizedValue;
  }

  static DateTime _requiredDateTime(Map<String, dynamic> json, String key) {
    final value = _requiredString(json, key);
    final parsedValue = DateTime.tryParse(value);

    if (parsedValue == null) {
      throw FormatException('Invalid $key');
    }

    return parsedValue;
  }

  @override
  bool operator ==(Object other) {
    return other is AuthUser &&
        other.id == id &&
        other.email == email &&
        other.fullName == fullName &&
        other.createdAt == createdAt &&
        other.updatedAt == updatedAt;
  }

  @override
  int get hashCode => Object.hash(id, email, fullName, createdAt, updatedAt);
}

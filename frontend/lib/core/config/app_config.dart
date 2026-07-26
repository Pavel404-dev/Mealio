import 'package:flutter_riverpod/flutter_riverpod.dart';

final appConfigProvider = Provider<AppConfig>((ref) {
  return const AppConfig();
});

class AppConfig {
  const AppConfig();

  static const String _configuredApiOrigin = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  String get apiBaseUrl {
    final normalizedOrigin = _configuredApiOrigin.trim().replaceFirst(
      RegExp(r'/+$'),
      '',
    );

    if (normalizedOrigin.endsWith('/api/v1')) {
      return normalizedOrigin;
    }

    return '$normalizedOrigin/api/v1';
  }
}

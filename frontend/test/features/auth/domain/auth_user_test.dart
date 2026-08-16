import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';

void main() {
  Map<String, Object?> userJson({required Object? emailVerified}) {
    return {
      'id': '7c59f60a-8428-4bce-a2bd-bfe7dd10b3af',
      'email': 'pavel@example.com',
      'full_name': 'Pavel Potapenko',
      'email_verified': emailVerified,
      'created_at': '2026-07-20T10:00:00Z',
      'updated_at': '2026-07-20T10:00:00Z',
    };
  }

  test('parses verified user state from backend', () {
    final user = AuthUser.fromJson(userJson(emailVerified: true));

    expect(user.emailVerified, isTrue);
  });

  test('parses unverified user state from backend', () {
    final user = AuthUser.fromJson(userJson(emailVerified: false));

    expect(user.emailVerified, isFalse);
  });

  test('rejects malformed email verification state', () {
    expect(
      () => AuthUser.fromJson(userJson(emailVerified: 'false')),
      throwsA(isA<FormatException>()),
    );
  });

  test('rejects missing email verification state', () {
    final json = userJson(emailVerified: false)..remove('email_verified');

    expect(() => AuthUser.fromJson(json), throwsA(isA<FormatException>()));
  });
}

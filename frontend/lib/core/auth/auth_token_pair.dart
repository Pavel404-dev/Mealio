class AuthTokenPair {
  const AuthTokenPair({required this.accessToken, required this.refreshToken});

  factory AuthTokenPair.fromJson(Object? data) {
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Invalid token response');
    }

    final accessToken = data['access_token'];
    final refreshToken = data['refresh_token'];
    final tokenType = data['token_type'];

    if (accessToken is! String ||
        accessToken.trim().isEmpty ||
        refreshToken is! String ||
        refreshToken.trim().isEmpty ||
        tokenType != 'bearer') {
      throw const FormatException('Invalid token response');
    }

    return AuthTokenPair(
      accessToken: accessToken.trim(),
      refreshToken: refreshToken.trim(),
    );
  }

  final String accessToken;
  final String refreshToken;
}

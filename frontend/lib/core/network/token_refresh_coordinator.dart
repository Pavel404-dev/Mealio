import 'package:dio/dio.dart';

import '../auth/auth_token_pair.dart';
import '../storage/secure_storage_provider.dart';
import 'session_request.dart';

enum TokenRefreshFailureType { invalidSession, transient, superseded }

class TokenRefreshFailure implements Exception {
  const TokenRefreshFailure._(this.type, {this.cause});

  const TokenRefreshFailure.invalidSession()
    : this._(TokenRefreshFailureType.invalidSession);

  const TokenRefreshFailure.transient(DioException cause)
    : this._(TokenRefreshFailureType.transient, cause: cause);

  const TokenRefreshFailure.superseded()
    : this._(TokenRefreshFailureType.superseded);

  final TokenRefreshFailureType type;
  final DioException? cause;
}

class TokenRefreshCoordinator {
  factory TokenRefreshCoordinator({
    required Dio refreshDio,
    required SecureStorageService storage,
    required void Function() onSessionInvalidated,
  }) {
    refreshDio.httpClientAdapter = SessionHttpClientAdapter(
      refreshDio.httpClientAdapter,
      storage,
    );
    return TokenRefreshCoordinator._(refreshDio, storage, onSessionInvalidated);
  }

  TokenRefreshCoordinator._(
    this._refreshDio,
    this._storage,
    this._onSessionInvalidated,
  );

  final Dio _refreshDio;
  final SecureStorageService _storage;
  final void Function() _onSessionInvalidated;

  final Map<int, Future<AuthTokenPair>> _inFlightRefresh = {};

  Future<void> invalidateSession() async {
    await _invalidateLocalSession(_storage.sessionLifetime);
  }

  Future<AuthTokenPair> refreshTokens({int? sessionLifetime}) async {
    final lifetime = sessionLifetime ?? _storage.sessionLifetime;
    _checkSession(lifetime);
    final existingRefresh = _inFlightRefresh[lifetime];
    if (existingRefresh != null) return existingRefresh;

    final refreshFuture = _refreshOnce(lifetime);
    _inFlightRefresh[lifetime] = refreshFuture;
    try {
      return await refreshFuture;
    } finally {
      if (identical(_inFlightRefresh[lifetime], refreshFuture)) {
        _inFlightRefresh.remove(lifetime);
      }
    }
  }

  void _checkSession(int lifetime) {
    if (!_storage.ownsSession(lifetime)) {
      throw const TokenRefreshFailure.superseded();
    }
  }

  Future<AuthTokenPair> _refreshOnce(int lifetime) async {
    final String? storedRefreshToken;
    try {
      storedRefreshToken = await _storage.readSessionRefreshToken(lifetime);
    } catch (_) {
      _checkSession(lifetime);
      return _failSession(lifetime);
    }
    _checkSession(lifetime);
    final refreshToken = storedRefreshToken?.trim();
    if (refreshToken == null || refreshToken.isEmpty) {
      return _failSession(lifetime);
    }

    final Response<Object?> response;
    try {
      response = await _refreshDio.post<Object?>(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
        options: Options(extra: {sessionLifetimeKey: lifetime}),
      );
    } on DioException catch (error) {
      _checkSession(lifetime);
      if (error.response?.statusCode == 401) return _failSession(lifetime);
      throw TokenRefreshFailure.transient(error);
    }

    final AuthTokenPair tokenPair;
    try {
      if (response.statusCode != 200) {
        throw const FormatException('Unexpected refresh status');
      }
      tokenPair = AuthTokenPair.fromJson(response.data);
    } on FormatException {
      _checkSession(lifetime);
      return _failSession(lifetime);
    }

    final bool replaced;
    try {
      replaced = await _storage.replaceTokenPairIfRefreshTokenMatches(
        sessionLifetime: lifetime,
        expectedRefreshToken: refreshToken,
        pair: tokenPair,
      );
    } catch (_) {
      await _revokeRefreshTokenBestEffort(tokenPair.refreshToken);
      _checkSession(lifetime);
      return _failSession(lifetime);
    }

    if (!replaced || !_storage.ownsSession(lifetime)) {
      await _revokeRefreshTokenBestEffort(tokenPair.refreshToken);
      throw const TokenRefreshFailure.superseded();
    }
    return tokenPair;
  }

  Future<Never> _failSession(int lifetime) async {
    final invalidated = await _invalidateLocalSession(lifetime);
    if (!invalidated) throw const TokenRefreshFailure.superseded();
    throw const TokenRefreshFailure.invalidSession();
  }

  Future<bool> _invalidateLocalSession(int lifetime) async {
    var invalidated = false;
    try {
      await _storage.deleteTokenPairIfSessionMatches(
        lifetime,
        onDeleted: () {
          invalidated = true;
          _onSessionInvalidated();
        },
      );
    } catch (_) {
      // The callback also runs after partial cleanup, but only for its owner.
    }
    return invalidated;
  }

  Future<void> _revokeRefreshTokenBestEffort(String refreshToken) async {
    try {
      await _refreshDio.post<Object?>(
        '/auth/logout',
        data: {'refresh_token': refreshToken},
      );
    } catch (_) {
      // The local session has already moved on, so remote cleanup is best effort.
    }
  }
}

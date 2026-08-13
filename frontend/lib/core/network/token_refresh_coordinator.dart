import 'package:dio/dio.dart';

import '../auth/auth_token_pair.dart';
import '../storage/secure_storage_provider.dart';

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

  Future<AuthTokenPair>? _inFlightRefresh;

  Future<void> invalidateSession() {
    return _invalidateLocalSession();
  }

  Future<AuthTokenPair> refreshTokens() async {
    final existingRefresh = _inFlightRefresh;
    if (existingRefresh != null) {
      return existingRefresh;
    }

    final refreshFuture = _refreshOnce();
    _inFlightRefresh = refreshFuture;

    try {
      return await refreshFuture;
    } finally {
      if (identical(_inFlightRefresh, refreshFuture)) {
        _inFlightRefresh = null;
      }
    }
  }

  Future<AuthTokenPair> _refreshOnce() async {
    final String refreshToken;

    try {
      final storedRefreshToken = (await _storage.readRefreshToken())?.trim();
      if (storedRefreshToken == null || storedRefreshToken.isEmpty) {
        await _invalidateLocalSession();
        throw const TokenRefreshFailure.invalidSession();
      }

      refreshToken = storedRefreshToken;
    } on TokenRefreshFailure {
      rethrow;
    } catch (_) {
      await _invalidateLocalSession();
      throw const TokenRefreshFailure.invalidSession();
    }

    final Response<Object?> response;
    try {
      response = await _refreshDio.post<Object?>(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );
    } on DioException catch (error) {
      if (error.response?.statusCode == 401) {
        await _invalidateLocalSession();
        throw const TokenRefreshFailure.invalidSession();
      }

      throw TokenRefreshFailure.transient(error);
    }

    final AuthTokenPair tokenPair;
    try {
      if (response.statusCode != 200) {
        throw const FormatException('Unexpected refresh status');
      }

      tokenPair = AuthTokenPair.fromJson(response.data);
    } on FormatException {
      await _invalidateLocalSession();
      throw const TokenRefreshFailure.invalidSession();
    }

    final bool replaced;
    try {
      replaced = await _storage.replaceTokenPairIfRefreshTokenMatches(
        expectedRefreshToken: refreshToken,
        pair: tokenPair,
      );
    } catch (_) {
      await _revokeRefreshTokenBestEffort(tokenPair.refreshToken);
      await _invalidateLocalSession();
      throw const TokenRefreshFailure.invalidSession();
    }

    if (!replaced) {
      await _revokeRefreshTokenBestEffort(tokenPair.refreshToken);
      throw const TokenRefreshFailure.superseded();
    }

    return tokenPair;
  }

  Future<void> _invalidateLocalSession() async {
    try {
      await _storage.deleteTokenPair();
    } catch (_) {
      // Session invalidation must still propagate to application state.
    }

    _onSessionInvalidated();
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

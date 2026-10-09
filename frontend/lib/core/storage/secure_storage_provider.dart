import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../auth/auth_token_pair.dart';

const String accessTokenStorageKey = 'mealio_access_token';
const String refreshTokenStorageKey = 'mealio_refresh_token';

final flutterSecureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

final secureStorageServiceProvider = Provider<SecureStorageService>((ref) {
  return SecureStorageService(ref.watch(flutterSecureStorageProvider));
});

class SecureStorageService {
  SecureStorageService(this._storage);

  final FlutterSecureStorage _storage;

  Future<void> _tokenPairMutationTail = Future<void>.value();
  int _tokenPairRevision = 0;

  int get tokenPairRevision => _tokenPairRevision;

  int _sessionLifetime = 0;
  // Includes credentials restored at startup.
  bool _credentialsAvailable = true;

  int get sessionLifetime => _sessionLifetime;
  bool ownsSession(int lifetime) => lifetime == _sessionLifetime;

  void checkSession(int lifetime) {
    if (!ownsSession(lifetime)) throw const SessionSuperseded();
  }

  void _endSession() {
    _sessionLifetime++;
    _credentialsAvailable = false;
  }

  // Reads share the mutation queue, so a partially written pair is never used.
  Future<String?> readSessionAccessToken(int lifetime) =>
      _readSessionToken(lifetime, readAccessToken);

  Future<String?> readSessionRefreshToken(int lifetime) =>
      _readSessionToken(lifetime, readRefreshToken);

  Future<String?> _readSessionToken(
    int lifetime,
    Future<String?> Function() read,
  ) => _serializeTokenPairMutation(() async {
    checkSession(lifetime);
    if (!_credentialsAvailable) return null;
    final token = await read();
    checkSession(lifetime);
    return token;
  });

  Future<void> writeAccessToken(String token) {
    return _storage.write(key: accessTokenStorageKey, value: token);
  }

  Future<String?> readAccessToken() {
    return _storage.read(key: accessTokenStorageKey);
  }

  Future<void> deleteAccessToken() {
    return _storage.delete(key: accessTokenStorageKey);
  }

  Future<void> writeRefreshToken(String token) {
    return _storage.write(key: refreshTokenStorageKey, value: token);
  }

  Future<String?> readRefreshToken() {
    return _storage.read(key: refreshTokenStorageKey);
  }

  Future<void> deleteRefreshToken() {
    return _storage.delete(key: refreshTokenStorageKey);
  }

  Future<void> writeTokenPair(AuthTokenPair pair) {
    _endSession();
    final lifetime = sessionLifetime;
    return _serializeTokenPairMutation(() async {
      await _writeTokenPairUnlocked(pair);
      if (ownsSession(lifetime)) _credentialsAvailable = true;
    });
  }

  Future<bool> writeTokenPairForSession(int lifetime, AuthTokenPair pair) {
    return _serializeTokenPairMutation(() async {
      if (!ownsSession(lifetime)) return false;
      await _writeTokenPairUnlocked(pair);
      if (!ownsSession(lifetime)) return false;
      _credentialsAvailable = true;
      return true;
    });
  }

  Future<bool> replaceTokenPairIfRefreshTokenMatches({
    required String expectedRefreshToken,
    required AuthTokenPair pair,
    int? sessionLifetime,
  }) {
    final lifetime = sessionLifetime ?? this.sessionLifetime;
    return _serializeTokenPairMutation(() async {
      if (!ownsSession(lifetime) || !_credentialsAvailable) return false;
      final currentRefreshToken = (await readRefreshToken())?.trim();

      if (!ownsSession(lifetime) ||
          currentRefreshToken != expectedRefreshToken.trim()) {
        return false;
      }

      await _writeTokenPairUnlocked(pair);
      return ownsSession(lifetime);
    });
  }

  // Ownership is checked inside the queue. Once deletion starts, newer writes
  // remain behind it; publication is checked again after platform I/O.
  Future<bool> deleteTokenPairIfSessionMatches(
    int lifetime, {
    void Function()? onDeleted,
  }) => _serializeTokenPairMutation(() async {
    if (!ownsSession(lifetime)) return false;
    _endSession();
    final endedLifetime = sessionLifetime;
    try {
      await _deleteTokenPairUnlocked();
    } finally {
      if (ownsSession(endedLifetime)) onDeleted?.call();
    }
    return true;
  });

  Future<void> deleteEmptyRefreshTokenForSession(int lifetime) =>
      _serializeTokenPairMutation(() async {
        checkSession(lifetime);
        final token = await readRefreshToken();
        checkSession(lifetime);
        if (token != null && token.trim().isEmpty) await deleteRefreshToken();
      });

  Future<void> deleteTokenPair() {
    _endSession();
    return _serializeTokenPairMutation(_deleteTokenPairUnlocked);
  }

  Future<String?> deleteTokenPairAndGetRefreshToken() {
    _endSession();
    return _serializeTokenPairMutation(() async {
      String? refreshToken;

      try {
        refreshToken = (await readRefreshToken())?.trim();
      } catch (_) {
        // Local cleanup still takes priority if the credential cannot be read.
      }

      await _deleteTokenPairUnlocked();
      return refreshToken;
    });
  }

  Future<T> _serializeTokenPairMutation<T>(Future<T> Function() mutation) {
    final previousMutation = _tokenPairMutationTail;
    final release = Completer<void>();

    _tokenPairMutationTail = release.future;

    return () async {
      await previousMutation;

      try {
        return await mutation();
      } finally {
        release.complete();
      }
    }();
  }

  Future<void> _writeTokenPairUnlocked(AuthTokenPair pair) async {
    try {
      // Refresh first keeps an interrupted write in the safer refresh-only state.
      await writeRefreshToken(pair.refreshToken);
      await writeAccessToken(pair.accessToken);
      _tokenPairRevision++;
    } catch (error, stackTrace) {
      await _deleteTokenPairUnlockedBestEffort();
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  Future<void> _deleteTokenPairUnlocked() async {
    Object? firstError;
    StackTrace? firstStackTrace;

    try {
      await deleteAccessToken();
    } catch (error, stackTrace) {
      firstError = error;
      firstStackTrace = stackTrace;
    }

    try {
      await deleteRefreshToken();
    } catch (error, stackTrace) {
      firstError ??= error;
      firstStackTrace ??= stackTrace;
    } finally {
      _tokenPairRevision++;
    }

    if (firstError != null) {
      Error.throwWithStackTrace(firstError, firstStackTrace!);
    }
  }

  Future<void> _deleteTokenPairUnlockedBestEffort() async {
    try {
      await _deleteTokenPairUnlocked();
    } catch (_) {
      // Preserve the original token-pair write failure.
    }
  }
}

/// An operation outlived its login session. Contains no credential details.
class SessionSuperseded implements Exception {
  const SessionSuperseded();
}

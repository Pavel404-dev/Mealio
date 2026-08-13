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
    return _serializeTokenPairMutation(() async {
      await _writeTokenPairUnlocked(pair);
    });
  }

  Future<bool> replaceTokenPairIfRefreshTokenMatches({
    required String expectedRefreshToken,
    required AuthTokenPair pair,
  }) {
    return _serializeTokenPairMutation(() async {
      final currentRefreshToken = (await readRefreshToken())?.trim();

      if (currentRefreshToken != expectedRefreshToken.trim()) {
        return false;
      }

      await _writeTokenPairUnlocked(pair);
      return true;
    });
  }

  Future<void> deleteTokenPair() {
    return _serializeTokenPairMutation(_deleteTokenPairUnlocked);
  }

  Future<String?> deleteTokenPairAndGetRefreshToken() {
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

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

  Future<void> writeTokenPair(AuthTokenPair pair) async {
    try {
      await writeRefreshToken(pair.refreshToken);
      await writeAccessToken(pair.accessToken);
      _tokenPairRevision++;
    } catch (error, stackTrace) {
      await _deleteTokenPairBestEffort();
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  Future<void> deleteTokenPair() async {
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

  Future<void> _deleteTokenPairBestEffort() async {
    try {
      await deleteTokenPair();
    } catch (_) {
      // Preserve the original token-pair write failure.
    }
  }
}

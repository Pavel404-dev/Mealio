import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const String accessTokenStorageKey = 'mealio_access_token';

final flutterSecureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

final secureStorageServiceProvider = Provider<SecureStorageService>((ref) {
  return SecureStorageService(ref.watch(flutterSecureStorageProvider));
});

class SecureStorageService {
  SecureStorageService(this._storage);

  final FlutterSecureStorage _storage;

  Future<void> writeAccessToken(String token) {
    return _storage.write(key: accessTokenStorageKey, value: token);
  }

  Future<String?> readAccessToken() {
    return _storage.read(key: accessTokenStorageKey);
  }

  Future<void> deleteAccessToken() {
    return _storage.delete(key: accessTokenStorageKey);
  }
}

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session_invalidation.dart';
import '../config/app_config.dart';
import '../storage/secure_storage_provider.dart';
import 'auth_interceptor.dart';
import 'token_refresh_coordinator.dart';

final bareDioProvider = Provider<Dio>((ref) {
  final appConfig = ref.watch(appConfigProvider);
  return Dio(_createBaseOptions(appConfig.apiBaseUrl));
});

final tokenRefreshCoordinatorProvider = Provider<TokenRefreshCoordinator>((
  ref,
) {
  return TokenRefreshCoordinator(
    refreshDio: ref.watch(bareDioProvider),
    storage: ref.watch(secureStorageServiceProvider),
    onSessionInvalidated: () {
      ref.read(sessionInvalidationProvider.notifier).invalidate();
    },
  );
});

final dioProvider = Provider<Dio>((ref) {
  final appConfig = ref.watch(appConfigProvider);
  final secureStorage = ref.watch(secureStorageServiceProvider);
  final refreshCoordinator = ref.watch(tokenRefreshCoordinatorProvider);

  final dio = Dio(_createBaseOptions(appConfig.apiBaseUrl));

  dio.interceptors.add(
    AuthInterceptor(
      dio: dio,
      storage: secureStorage,
      refreshCoordinator: refreshCoordinator,
    ),
  );

  return dio;
});

BaseOptions _createBaseOptions(String baseUrl) {
  return BaseOptions(
    baseUrl: baseUrl,
    connectTimeout: const Duration(seconds: 10),
    sendTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 20),
    responseType: ResponseType.json,
    headers: const {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
  );
}

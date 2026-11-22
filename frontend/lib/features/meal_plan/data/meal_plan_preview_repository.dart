import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../domain/meal_plan_preview.dart';
import '../domain/meal_plan_preview_failure.dart';

final mealPlanPreviewRepositoryProvider = Provider<MealPlanPreviewRepository>((
  ref,
) {
  return MealPlanPreviewRepository(
    apiClient: ref.watch(apiClientProvider),
    storage: ref.watch(secureStorageServiceProvider),
    apiV2BaseUrl: ref.watch(appConfigProvider).apiV2BaseUrl,
  );
});

class MealPlanPreviewRepository {
  MealPlanPreviewRepository({
    required ApiClient apiClient,
    required SecureStorageService storage,
    required String apiV2BaseUrl,
  }) : this._(
         apiClient,
         storage,
         '$apiV2BaseUrl/meal-plans/ai/generate-preview',
       );

  MealPlanPreviewRepository._(this._apiClient, this._storage, this._url);

  final ApiClient _apiClient;
  final SecureStorageService _storage;
  final String _url;

  Future<MealPlanPreview> generate({
    required MealPlanPreviewRequest request,
    required String idempotencyKey,
    required int lifetime,
    required CancelToken cancelToken,
  }) async {
    try {
      _storage.checkSession(lifetime);
      final result = await _apiClient.post<Object?>(
        _url,
        data: request.toJson(),
        headers: {'Idempotency-Key': idempotencyKey},
        // The server deadline can be configured up to 120 seconds.
        receiveTimeout: const Duration(seconds: 130),
        sessionLifetime: lifetime,
        cancelToken: cancelToken,
      );
      _storage.checkSession(lifetime);
      if (cancelToken.isCancelled) throw cancelToken.cancelError!;
      if (result.statusCode != 200) {
        throw const FormatException('Unexpected meal plan preview status');
      }
      return MealPlanPreview.fromJson(result.data, request);
    } on DioException catch (error) {
      _storage.checkSession(lifetime);
      if (error.error is SessionSuperseded) throw const SessionSuperseded();
      if (error.type == DioExceptionType.cancel) rethrow;
      throw MealPlanPreviewFailure(switch (error.response?.statusCode) {
        401 => MealPlanPreviewFailureType.authentication,
        422 => MealPlanPreviewFailureType.noEligibleRecipes,
        409 =>
          error.response?.headers.value('retry-after') == null
              ? MealPlanPreviewFailureType.inputsChanged
              : MealPlanPreviewFailureType.inProgress,
        429 => MealPlanPreviewFailureType.rateLimited,
        502 || 503 => MealPlanPreviewFailureType.providerUnavailable,
        _ => switch (error.type) {
          DioExceptionType.connectionTimeout ||
          DioExceptionType.sendTimeout ||
          DioExceptionType.receiveTimeout ||
          DioExceptionType.transformTimeout ||
          DioExceptionType.connectionError =>
            MealPlanPreviewFailureType.connection,
          _ => MealPlanPreviewFailureType.unexpected,
        },
      });
    } on FormatException {
      throw const MealPlanPreviewFailure(MealPlanPreviewFailureType.unexpected);
    }
  }
}

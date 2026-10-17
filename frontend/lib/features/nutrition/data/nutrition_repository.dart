import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../domain/nutrition_failure.dart';
import '../domain/nutrition_profile.dart';

final nutritionRepositoryProvider = Provider<NutritionRepository>((ref) {
  return NutritionRepository(
    apiClient: ref.watch(apiClientProvider),
    storage: ref.watch(secureStorageServiceProvider),
  );
});

class NutritionRepository {
  NutritionRepository({
    required ApiClient apiClient,
    required SecureStorageService storage,
  }) : this._(apiClient, storage);

  NutritionRepository._(this._apiClient, this._storage);

  final ApiClient _apiClient;
  final SecureStorageService _storage;
  static const _path = '/user-preferences/nutrition';

  Future<NutritionProfile> load({required int lifetime}) =>
      _request(lifetime, null);

  Future<NutritionProfile> save({
    required int lifetime,
    required Map<NutritionField, String> changes,
  }) => _request(lifetime, changes);

  Future<NutritionProfile> _request(
    int lifetime,
    Map<NutritionField, String>? changes,
  ) async {
    try {
      if (changes != null &&
          (changes.isEmpty ||
              changes.entries.any(
                (e) => nutritionInputError(e.key, e.value) != null,
              ))) {
        throw const NutritionFailure(NutritionFailureType.validation);
      }
      // No await between this owner check and ApiClient invocation. ApiClient
      // then pins that same lifetime through async transport preparation/retry.
      _storage.checkSession(lifetime);
      final response = await (changes == null
          ? _apiClient.get<Object?>(_path, sessionLifetime: lifetime)
          : _apiClient.patch<Object?>(
              _path,
              data: {
                for (final entry in changes.entries)
                  entry.key.wireName: nutritionWireValue(entry.value),
              },
            ));
      _storage.checkSession(lifetime);
      if (response.statusCode != 200) {
        throw const FormatException('Unexpected nutrition status');
      }
      return NutritionProfile.fromJson(response.data);
    } on SessionSuperseded {
      rethrow;
    } on NutritionFailure {
      rethrow;
    } on DioException catch (error) {
      _storage.checkSession(lifetime);
      if (error.error is SessionSuperseded) throw const SessionSuperseded();
      final type = switch (error.response?.statusCode) {
        401 => NutritionFailureType.authentication,
        422 => NutritionFailureType.validation,
        429 => NutritionFailureType.rateLimited,
        _ => switch (error.type) {
          DioExceptionType.connectionTimeout ||
          DioExceptionType.sendTimeout ||
          DioExceptionType.receiveTimeout ||
          DioExceptionType.transformTimeout ||
          DioExceptionType.connectionError => NutritionFailureType.connection,
          _ => NutritionFailureType.unexpected,
        },
      };
      throw NutritionFailure(type);
    } catch (_) {
      _storage.checkSession(lifetime);
      throw const NutritionFailure(NutritionFailureType.unexpected);
    }
  }
}

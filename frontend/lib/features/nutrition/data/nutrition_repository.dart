import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../domain/nutrition_failure.dart';
import '../domain/nutrition_profile.dart';
import '../domain/nutrition_preferences.dart';
import '../domain/nutrition_calculation.dart';

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

  Future<NutritionProfile> load({required int lifetime}) => _request(
    lifetime,
    () => _apiClient.get<Object?>(_path, sessionLifetime: lifetime),
    NutritionProfile.fromJson,
  );

  Future<NutritionProfile> save({
    required int lifetime,
    required NutritionPatch changes,
  }) => _request(lifetime, () {
    if (changes.isEmpty) {
      throw const NutritionFailure(NutritionFailureType.validation);
    }
    return _apiClient.patch<Object?>(_path, data: changes.json);
  }, NutritionProfile.fromJson);

  Future<NutritionCalculation> calculate({
    required int lifetime,
    required DateTime date,
  }) {
    final day = nutritionCalculationDate(date);
    return _request(
      lifetime,
      () => _apiClient.post<Object?>(
        '$_path/calculate',
        data: {
          'calculation_date': day,
          'rules_version': NutritionCalculation.rulesVersion,
        },
      ),
      (json) => NutritionCalculation.fromJson(json, date: day),
    );
  }

  Future<T> _request<T>(
    int lifetime,
    Future<Response<Object?>> Function() dispatch,
    T Function(Object?) parse,
  ) async {
    try {
      // Dispatch is synchronous up to ApiClient's lifetime capture. No await
      // may be inserted between this final owner check and invocation.
      _storage.checkSession(lifetime);
      final response = await dispatch();
      _storage.checkSession(lifetime);
      if (response.statusCode != 200) {
        throw const FormatException('Unexpected nutrition status');
      }
      return parse(response.data);
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

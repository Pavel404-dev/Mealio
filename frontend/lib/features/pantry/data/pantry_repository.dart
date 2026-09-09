import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../domain/pantry_failure.dart';
import '../domain/pantry_item.dart';

final pantryRepositoryProvider = Provider<PantryRepository>((ref) {
  return PantryRepository(apiClient: ref.watch(apiClientProvider));
});

class PantryRepository {
  factory PantryRepository({required ApiClient apiClient}) {
    return PantryRepository._(apiClient);
  }

  PantryRepository._(this._apiClient);

  final ApiClient _apiClient;

  Future<List<PantryItem>> getPantry() async {
    try {
      final response = await _apiClient.get<Object?>('/pantry');

      if (response.statusCode != 200) {
        throw const FormatException('Unexpected pantry status code');
      }

      final data = response.data;
      if (data is! List<dynamic>) {
        throw const FormatException('Expected a list for pantry');
      }

      return data.map(PantryItem.fromJson).toList(growable: false);
    } on DioException catch (error) {
      throw _mapDioException(error);
    } on FormatException {
      throw PantryFailure.unexpected();
    } on PantryFailure {
      rethrow;
    } catch (_) {
      throw PantryFailure.unexpected();
    }
  }

  PantryFailure _mapDioException(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
      case DioExceptionType.connectionError:
        return PantryFailure.connection();
      case DioExceptionType.badResponse:
        return PantryFailure.backend();
      case DioExceptionType.badCertificate:
      case DioExceptionType.cancel:
      case DioExceptionType.unknown:
        return PantryFailure.unexpected();
    }
  }
}

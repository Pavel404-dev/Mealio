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

  Future<List<Ingredient>> searchIngredients({String? search}) async {
    try {
      final normalizedSearch = search?.trim() ?? '';
      final response = await _apiClient.get<Object?>(
        '/ingredients',
        queryParameters: {
          if (normalizedSearch.isNotEmpty) 'search': normalizedSearch,
          'limit': 50,
          'offset': 0,
        },
      );

      if (response.statusCode != 200) {
        throw const FormatException('Unexpected ingredient status code');
      }
      final data = response.data;
      if (data is! List<dynamic>) {
        throw const FormatException('Expected an ingredient list');
      }
      return data.map(Ingredient.fromJson).toList(growable: false);
    } on DioException catch (error) {
      throw _mapDioException(error, operation: _PantryOperation.search);
    } on FormatException {
      throw PantryFailure.searchUnexpected();
    } on PantryFailure {
      rethrow;
    } catch (_) {
      throw PantryFailure.searchUnexpected();
    }
  }

  Future<PantryItem> addPantryItem({
    required String ingredientId,
    required String quantityG,
    DateTime? expiresAt,
  }) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/pantry',
        data: {
          'ingredient_id': ingredientId,
          'quantity_g': quantityG,
          'expires_at': expiresAt?.toUtc().toIso8601String(),
        },
      );
      if (response.statusCode != 201) {
        throw const FormatException('Unexpected create status code');
      }
      return PantryItem.fromJson(response.data);
    } on DioException catch (error) {
      throw _mapDioException(error, operation: _PantryOperation.create);
    } on FormatException {
      throw PantryFailure.createUnexpected();
    } on PantryFailure {
      rethrow;
    } catch (_) {
      throw PantryFailure.createUnexpected();
    }
  }

  Future<PantryItem> updatePantryItem({
    required String pantryItemId,
    required String quantityG,
    DateTime? expiresAt,
  }) async {
    try {
      final response = await _apiClient.patch<Object?>(
        '/pantry/$pantryItemId',
        data: {
          'quantity_g': quantityG,
          'expires_at': expiresAt?.toUtc().toIso8601String(),
        },
      );
      if (response.statusCode != 200) {
        throw const FormatException('Unexpected update status code');
      }
      return PantryItem.fromJson(response.data);
    } on DioException catch (error) {
      throw _mapDioException(error, operation: _PantryOperation.update);
    } on FormatException {
      throw PantryFailure.updateUnexpected();
    } on PantryFailure {
      rethrow;
    } catch (_) {
      throw PantryFailure.updateUnexpected();
    }
  }

  Future<void> deletePantryItem({required String pantryItemId}) async {
    try {
      final response = await _apiClient.delete<Object?>(
        '/pantry/$pantryItemId',
      );
      if (response.statusCode != 204) {
        throw const FormatException('Unexpected delete status code');
      }
    } on DioException catch (error) {
      throw _mapDioException(error, operation: _PantryOperation.delete);
    } on FormatException {
      throw PantryFailure.deleteUnexpected();
    } on PantryFailure {
      rethrow;
    } catch (_) {
      throw PantryFailure.deleteUnexpected();
    }
  }

  PantryFailure _mapDioException(
    DioException error, {
    _PantryOperation operation = _PantryOperation.list,
  }) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
      case DioExceptionType.connectionError:
        return PantryFailure.connection();
      case DioExceptionType.badResponse:
        final statusCode = error.response?.statusCode;
        if (operation == _PantryOperation.create) {
          return switch (statusCode) {
            401 => PantryFailure.authentication(),
            404 => PantryFailure.ingredientUnavailable(),
            409 => PantryFailure.duplicate(),
            422 => PantryFailure.validation(),
            _ => PantryFailure.createBackend(),
          };
        }
        if (operation == _PantryOperation.search) {
          return statusCode == 401
              ? PantryFailure.authentication()
              : PantryFailure.searchBackend();
        }
        if (operation == _PantryOperation.update) {
          return switch (statusCode) {
            401 => PantryFailure.authentication(),
            404 => PantryFailure.pantryItemUnavailable(),
            422 => PantryFailure.validation(),
            _ => PantryFailure.updateBackend(),
          };
        }
        if (operation == _PantryOperation.delete) {
          return switch (statusCode) {
            401 => PantryFailure.authentication(),
            404 => PantryFailure.pantryItemUnavailable(),
            422 => PantryFailure.deleteBackend(),
            _ => PantryFailure.deleteBackend(),
          };
        }
        return PantryFailure.backend();
      case DioExceptionType.badCertificate:
      case DioExceptionType.cancel:
      case DioExceptionType.unknown:
        return switch (operation) {
          _PantryOperation.list => PantryFailure.unexpected(),
          _PantryOperation.search => PantryFailure.searchUnexpected(),
          _PantryOperation.create => PantryFailure.createUnexpected(),
          _PantryOperation.update => PantryFailure.updateUnexpected(),
          _PantryOperation.delete => PantryFailure.deleteUnexpected(),
        };
    }
  }
}

enum _PantryOperation { list, search, create, update, delete }

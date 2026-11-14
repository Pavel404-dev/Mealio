import 'dart:math' as math;

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../../pantry/domain/pantry_item.dart';
import '../domain/recipe.dart';
import '../domain/recipe_detail.dart';
import '../domain/recipe_failure.dart';

final recipeRepositoryProvider = Provider<RecipeRepository>((ref) {
  return RecipeRepository(
    apiClient: ref.watch(apiClientProvider),
    storage: ref.watch(secureStorageServiceProvider),
  );
});

class RecipeRepository {
  RecipeRepository({
    required ApiClient apiClient,
    required SecureStorageService storage,
  }) : this._(apiClient, storage);

  RecipeRepository._(this._apiClient, this._storage);

  final ApiClient _apiClient;
  final SecureStorageService _storage;

  Future<List<Recipe>> getRecipes({
    required int lifetime,
    required int limit,
    required int offset,
  }) => _read(
    '/recipes',
    lifetime: lifetime,
    queryParameters: {'limit': limit, 'offset': offset},
    parse: (data) {
      if (data is! List) {
        throw const FormatException('Invalid recipe list response');
      }
      return List.unmodifiable(data.map(Recipe.fromJson));
    },
  );

  /// One read attempt owns a single lifetime and cancellation token, including
  /// catalog lookups after awaiting the recipe. Names are not a paginated search.
  Future<RecipeDetail> getRecipeDetail({
    required String recipeId,
    required int lifetime,
    CancelToken? cancelToken,
  }) async {
    final recipe = await _read(
      '/recipes/${Uri.encodeComponent(recipeId)}',
      lifetime: lifetime,
      cancelToken: cancelToken,
      notFound: RecipeFailureType.unavailable,
      parse: (data) {
        final recipe = Recipe.fromJson(data);
        if (recipe.id != recipeId ||
            recipe.ingredients.any((item) => item.recipeId != recipeId)) {
          throw const FormatException('Mismatched recipe response');
        }
        return recipe;
      },
    );
    final ids = recipe.ingredients
        .map((item) => item.ingredientId)
        .toSet()
        .toList();
    final names = <String, String>{};
    // Bounded batches also stop new dispatch after a failed/cancelled batch.
    for (var start = 0; start < ids.length; start += 4) {
      final batch = ids.sublist(start, math.min(start + 4, ids.length));
      final entries = await Future.wait(
        batch.map((id) async {
          final name = await _read(
            '/ingredients/${Uri.encodeComponent(id)}',
            lifetime: lifetime,
            cancelToken: cancelToken,
            notFound: RecipeFailureType.ingredientUnavailable,
            parse: (data) {
              final ingredient = Ingredient.fromJson(data);
              if (ingredient.id != id) {
                throw const FormatException('Mismatched ingredient response');
              }
              return ingredient.name;
            },
          );
          return MapEntry(id, name);
        }),
      );
      names.addEntries(entries);
    }
    _checkRequest(lifetime, cancelToken);
    return RecipeDetail(recipe: recipe, ingredientNames: names);
  }

  void _checkRequest(int lifetime, CancelToken? cancelToken) {
    _storage.checkSession(lifetime);
    if (cancelToken?.isCancelled == true) throw cancelToken!.cancelError!;
  }

  Future<T> _read<T>(
    String path, {
    required int lifetime,
    required T Function(Object?) parse,
    Map<String, dynamic>? queryParameters,
    CancelToken? cancelToken,
    RecipeFailureType notFound = RecipeFailureType.unexpected,
  }) async {
    try {
      _checkRequest(lifetime, cancelToken);
      final response = await _apiClient.get<Object?>(
        path,
        queryParameters: queryParameters,
        sessionLifetime: lifetime,
        cancelToken: cancelToken,
      );
      _checkRequest(lifetime, cancelToken);
      if (response.statusCode != 200) {
        throw const FormatException('Unexpected recipe response status');
      }
      return parse(response.data);
    } on SessionSuperseded {
      rethrow;
    } on DioException catch (error) {
      _storage.checkSession(lifetime);
      if (error.error is SessionSuperseded) throw const SessionSuperseded();
      if (cancelToken?.isCancelled == true) rethrow;
      final type = switch (error.response?.statusCode) {
        401 => RecipeFailureType.authentication,
        404 => notFound,
        429 => RecipeFailureType.rateLimited,
        _ => switch (error.type) {
          DioExceptionType.connectionTimeout ||
          DioExceptionType.sendTimeout ||
          DioExceptionType.receiveTimeout ||
          DioExceptionType.transformTimeout ||
          DioExceptionType.connectionError => RecipeFailureType.connection,
          _ => RecipeFailureType.unexpected,
        },
      };
      throw RecipeFailure(type);
    } catch (_) {
      _storage.checkSession(lifetime);
      throw const RecipeFailure(RecipeFailureType.unexpected);
    }
  }
}

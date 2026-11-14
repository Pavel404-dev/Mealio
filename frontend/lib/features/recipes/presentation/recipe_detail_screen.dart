import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/localization/l10n.dart';
import '../../../core/localization/language_button.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../../auth/presentation/auth_controller.dart';
import '../data/recipe_repository.dart';
import 'recipe_detail_controller.dart';
import 'recipe_localization.dart';
import 'recipe_nutrition_summary.dart';

class RecipeDetailScreen extends ConsumerWidget {
  const RecipeDetailScreen({super.key, required this.recipeId});

  final String recipeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final storage = ref.watch(secureStorageServiceProvider);
    if (auth.isLoading || auth.asData?.value.isAuthenticated != true) {
      return const SizedBox.shrink();
    }
    return _DetailVisit(
      key: ValueKey((storage.sessionLifetime, recipeId)),
      recipeId: recipeId,
    );
  }
}

class _DetailVisit extends ConsumerStatefulWidget {
  const _DetailVisit({super.key, required this.recipeId});

  final String recipeId;

  @override
  ConsumerState<_DetailVisit> createState() => _DetailVisitState();
}

class _DetailVisitState extends ConsumerState<_DetailVisit> {
  late final RecipeDetailController _controller;

  @override
  void initState() {
    super.initState();
    _controller = RecipeDetailController(
      recipeId: widget.recipeId,
      repository: ref.read(recipeRepositoryProvider),
      storage: ref.read(secureStorageServiceProvider),
      isAuthenticated: () {
        final auth = ref.read(authControllerProvider);
        return !auth.isLoading && auth.asData?.value.isAuthenticated == true;
      },
    );
    ref.listenManual(
      authControllerProvider,
      (_, _) => _controller.checkOwnership(),
    );
    unawaited(_controller.load());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, _) {
      if (!_controller.isCurrent) return const SizedBox.shrink();
      return Scaffold(
        key: const Key('recipe-detail-screen'),
        appBar: AppBar(
          title: Text(context.l10n.recipeDetails),
          leading: IconButton(
            key: const Key('recipe-detail-back'),
            tooltip: context.l10n.back,
            onPressed: () =>
                context.canPop() ? context.pop() : context.go('/recipes'),
            icon: const Icon(Icons.arrow_back_rounded),
          ),
          actions: const [LanguageButton()],
        ),
        body: SafeArea(child: _body(context)),
      );
    },
  );

  Widget _body(BuildContext context) {
    final l10n = context.l10n;
    if (_controller.failure case final failure?) {
      return ListView(
        key: const Key('recipe-detail-error'),
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            failure.localized(l10n, detail: true),
            key: const Key('recipe-detail-error-message'),
          ),
          const SizedBox(height: 12),
          FilledButton(
            key: const Key('recipe-detail-retry'),
            onPressed: () => unawaited(_controller.load()),
            child: Text(l10n.retry),
          ),
        ],
      );
    }
    final detail = _controller.detail;
    if (detail == null) {
      return Center(
        child: CircularProgressIndicator(
          key: const Key('recipe-detail-loading'),
          semanticsLabel: l10n.recipeDetailLoading,
        ),
      );
    }
    final recipe = detail.recipe;
    return ListView(
      key: const Key('recipe-detail-content'),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
      children: [
        Text(
          recipe.title,
          key: const Key('recipe-detail-title'),
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        if (recipe.description?.trim().isNotEmpty == true) ...[
          const SizedBox(height: 12),
          Text(recipe.description!),
        ],
        const SizedBox(height: 16),
        RecipeNutritionSummary(recipe: recipe),
        const SizedBox(height: 24),
        Text(
          l10n.recipeIngredients,
          style: Theme.of(context).textTheme.titleLarge,
        ),
        if (recipe.ingredients.isEmpty)
          Text(
            l10n.recipeNoIngredients,
            key: const Key('recipe-detail-empty-ingredients'),
          ),
        for (final item in recipe.ingredients)
          Padding(
            key: Key('recipe-detail-ingredient-${item.id}'),
            padding: const EdgeInsets.only(top: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(detail.ingredientNames[item.ingredientId]!),
                Text(
                  l10n.quantityGrams(
                    formatRecipeNumber(context, item.quantityG),
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 24),
        Text(
          l10n.recipeInstructions,
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 8),
        Text(recipe.instructions, key: const Key('recipe-detail-instructions')),
      ],
    );
  }
}

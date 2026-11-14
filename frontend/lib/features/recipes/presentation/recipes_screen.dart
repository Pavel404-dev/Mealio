import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/localization/l10n.dart';
import '../../../core/localization/language_button.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../../auth/presentation/auth_controller.dart';
import '../data/recipe_repository.dart';
import '../domain/recipe.dart';
import '../domain/recipe_failure.dart';
import 'recipe_list_controller.dart';
import 'recipe_localization.dart';
import 'recipe_nutrition_summary.dart';

class RecipesScreen extends ConsumerWidget {
  const RecipesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final storage = ref.watch(secureStorageServiceProvider);
    if (auth.isLoading || auth.asData?.value.isAuthenticated != true) {
      return const SizedBox.shrink();
    }
    return _RecipeList(key: ValueKey(storage.sessionLifetime));
  }
}

class _RecipeList extends ConsumerStatefulWidget {
  const _RecipeList({super.key});

  @override
  ConsumerState<_RecipeList> createState() => _RecipeListState();
}

class _RecipeListState extends ConsumerState<_RecipeList> {
  late final RecipeListController _controller;

  @override
  void initState() {
    super.initState();
    _controller = RecipeListController(
      repository: ref.read(recipeRepositoryProvider),
      storage: ref.read(secureStorageServiceProvider),
      isAuthenticated: () {
        final auth = ref.read(authControllerProvider);
        return !auth.isLoading && auth.asData?.value.isAuthenticated == true;
      },
    );
    ref.listenManual(authControllerProvider, (_, _) {
      _controller.checkOwnership();
    });
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
        key: const Key('recipes-screen'),
        appBar: AppBar(
          title: Text(context.l10n.recipes),
          actions: const [LanguageButton()],
        ),
        body: SafeArea(child: _body(context)),
      );
    },
  );

  Widget _body(BuildContext context) {
    if (!_controller.loaded) {
      if (_controller.failure case final failure?) {
        return ListView(
          key: const Key('recipes-error-state'),
          padding: const EdgeInsets.all(24),
          children: [_error(context, failure)],
        );
      }
      return Center(child: _loading(context));
    }
    if (_controller.items.isEmpty) {
      return ListView(
        key: const Key('recipes-empty-state'),
        padding: const EdgeInsets.all(24),
        children: [
          const Icon(Icons.menu_book_outlined, size: 56),
          const SizedBox(height: 16),
          Text(
            context.l10n.recipesEmpty,
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(context.l10n.recipesEmptyDescription),
        ],
      );
    }
    return ListView.builder(
      key: const Key('recipes-list'),
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
      itemCount: _controller.items.length + 1,
      itemBuilder: (context, index) {
        if (index < _controller.items.length) {
          return _RecipeCard(recipe: _controller.items[index]);
        }
        return Padding(
          padding: const EdgeInsets.only(top: 16),
          child: _footer(context),
        );
      },
    );
  }

  Widget _footer(BuildContext context) {
    if (_controller.loading) return Center(child: _loading(context));
    if (_controller.failure case final failure?) {
      return _error(context, failure);
    }
    if (_controller.hasMore) {
      return FilledButton(
        key: const Key('recipes-load-more'),
        onPressed: () => unawaited(_controller.loadMore()),
        child: Text(context.l10n.recipesLoadMore),
      );
    }
    return const SizedBox.shrink();
  }

  Widget _loading(BuildContext context) => CircularProgressIndicator(
    key: const Key('recipes-loading'),
    semanticsLabel: context.l10n.recipesLoading,
  );

  Widget _error(BuildContext context, RecipeFailure failure) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        failure.localized(context.l10n),
        key: const Key('recipes-error-message'),
      ),
      const SizedBox(height: 12),
      FilledButton(
        key: const Key('recipes-retry'),
        onPressed: () => unawaited(_controller.retry()),
        child: Text(context.l10n.retry),
      ),
    ],
  );
}

class _RecipeCard extends StatelessWidget {
  const _RecipeCard({required this.recipe});

  final Recipe recipe;

  @override
  Widget build(BuildContext context) {
    return Card(
      key: Key('recipe-${recipe.id}'),
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/recipes/${Uri.encodeComponent(recipe.id)}'),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(recipe.title, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              RecipeNutritionSummary(recipe: recipe),
            ],
          ),
        ),
      ),
    );
  }
}

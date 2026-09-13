import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../domain/pantry_failure.dart';
import '../domain/pantry_item.dart';
import 'pantry_providers.dart';

class PantryScreen extends ConsumerWidget {
  const PantryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pantryItems = ref.watch(pantryItemsProvider);

    return Scaffold(
      key: const Key('pantry-screen'),
      appBar: AppBar(title: const Text('Pantry')),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('pantry-add-button'),
        onPressed: () => context.push('/pantry/add'),
        icon: const Icon(Icons.add),
        label: const Text('Add ingredient'),
      ),
      body: SafeArea(
        child: pantryItems.when(
          loading: () => const Center(
            child: CircularProgressIndicator(
              key: Key('pantry-loading-indicator'),
            ),
          ),
          error: (error, stackTrace) => _PantryError(
            failure: error is PantryFailure
                ? error
                : PantryFailure.unexpected(),
            onRetry: () => ref.invalidate(pantryItemsProvider),
          ),
          data: (items) =>
              items.isEmpty ? const _EmptyPantry() : _PantryList(items: items),
        ),
      ),
    );
  }
}

class _EmptyPantry extends StatelessWidget {
  const _EmptyPantry();

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const Key('pantry-empty-state'),
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.kitchen_outlined, size: 56, color: AppColors.sage),
            const SizedBox(height: 16),
            Text(
              'Your pantry is empty',
              style: Theme.of(context).textTheme.titleLarge,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Ingredients you have at home will appear here.',
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

class _PantryError extends StatelessWidget {
  const _PantryError({required this.failure, required this.onRetry});

  final PantryFailure failure;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const Key('pantry-error-state'),
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.error_outline_rounded,
              size: 52,
              color: AppColors.muted,
            ),
            const SizedBox(height: 16),
            Text(
              failure.message,
              key: const Key('pantry-error-message'),
              style: Theme.of(context).textTheme.bodyLarge,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            FilledButton(
              key: const Key('pantry-retry-button'),
              onPressed: onRetry,
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

class _PantryList extends StatelessWidget {
  const _PantryList({required this.items});

  final List<PantryItem> items;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      key: const Key('pantry-list'),
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
      itemCount: items.length,
      separatorBuilder: (context, index) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final item = items[index];
        return Card(
          key: Key('pantry-item-${item.id}'),
          child: ListTile(
            onTap: () => context.push('/pantry/${item.id}/edit', extra: item),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 18,
              vertical: 8,
            ),
            leading: const CircleAvatar(
              backgroundColor: AppColors.cream,
              foregroundColor: AppColors.forest,
              child: Icon(Icons.kitchen_outlined),
            ),
            title: Text(item.ingredient.name),
            subtitle: Text(
              item.expiresAt == null
                  ? '${_formatQuantity(item.quantityG)} g'
                  : '${_formatQuantity(item.quantityG)} g\n'
                        'Expires ${_formatDate(item.expiresAt!)}',
            ),
          ),
        );
      },
    );
  }
}

String _formatDate(DateTime date) {
  final utcDate = date.toUtc();
  return '${utcDate.year.toString().padLeft(4, '0')}-'
      '${utcDate.month.toString().padLeft(2, '0')}-'
      '${utcDate.day.toString().padLeft(2, '0')}';
}

String _formatQuantity(double quantity) {
  if (quantity == quantity.truncateToDouble()) {
    return quantity.toStringAsFixed(0);
  }

  return quantity
      .toStringAsFixed(2)
      .replaceFirst(RegExp(r'0+$'), '')
      .replaceFirst(RegExp(r'\.$'), '');
}

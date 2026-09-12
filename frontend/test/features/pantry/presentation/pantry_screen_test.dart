import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/features/pantry/domain/pantry_failure.dart';
import 'package:mealio/features/pantry/domain/pantry_item.dart';
import 'package:mealio/features/pantry/presentation/pantry_providers.dart';
import 'package:mealio/features/pantry/presentation/pantry_screen.dart';

void main() {
  final pantryItem = PantryItem(
    id: 'pantry-1',
    userId: 'user-1',
    ingredientId: 'ingredient-1',
    quantityG: 250.5,
    expiresAt: null,
    createdAt: DateTime.parse('2026-09-10T10:00:00Z'),
    updatedAt: DateTime.parse('2026-09-10T10:00:00Z'),
    ingredient: Ingredient(
      id: 'ingredient-1',
      name: 'Oats',
      category: null,
      createdAt: DateTime.parse('2026-09-01T10:00:00Z'),
      nutritionValue: null,
    ),
  );

  Widget createScreen(Future<List<PantryItem>> Function() load) {
    return ProviderScope(
      overrides: [pantryItemsProvider.overrideWith((ref) => load())],
      child: const MaterialApp(home: PantryScreen()),
    );
  }

  testWidgets('shows loading while pantry is unresolved', (tester) async {
    final completer = Completer<List<PantryItem>>();

    await tester.pumpWidget(createScreen(() => completer.future));
    await tester.pump();

    expect(find.byKey(const Key('pantry-loading-indicator')), findsOneWidget);

    completer.complete([]);
    await tester.pumpAndSettle();
  });

  testWidgets('Add action is visible in loading, empty, list, and error', (
    tester,
  ) async {
    final completer = Completer<List<PantryItem>>();
    await tester.pumpWidget(createScreen(() => completer.future));
    await tester.pump();
    expect(find.byKey(const Key('pantry-add-button')), findsOneWidget);
    completer.complete([]);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pantry-add-button')), findsOneWidget);

    await tester.pumpWidget(createScreen(() async => [pantryItem]));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pantry-add-button')), findsOneWidget);

    await tester.pumpWidget(
      createScreen(() async => throw PantryFailure.backend()),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pantry-add-button')), findsOneWidget);
  });

  testWidgets('Add action pushes /pantry/add', (tester) async {
    final router = GoRouter(
      initialLocation: '/pantry',
      routes: [
        GoRoute(
          path: '/pantry',
          builder: (context, state) => const PantryScreen(),
        ),
        GoRoute(
          path: '/pantry/add',
          builder: (context, state) =>
              const Scaffold(key: Key('fake-add-screen')),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [pantryItemsProvider.overrideWith((ref) async => [])],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('pantry-add-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('fake-add-screen')), findsOneWidget);
  });

  testWidgets('shows an empty state', (tester) async {
    await tester.pumpWidget(createScreen(() async => []));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('pantry-empty-state')), findsOneWidget);
    expect(find.text('Your pantry is empty'), findsOneWidget);
  });

  testWidgets('shows ingredient name and quantity in list state', (
    tester,
  ) async {
    await tester.pumpWidget(createScreen(() async => [pantryItem]));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('pantry-list')), findsOneWidget);
    expect(find.text('Oats'), findsOneWidget);
    expect(find.text('250.5 g'), findsOneWidget);
  });

  testWidgets('nullable nested values render safely', (tester) async {
    await tester.pumpWidget(createScreen(() async => [pantryItem]));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('pantry-item-pantry-1')), findsOneWidget);
  });

  testWidgets('shows a connection-specific safe failure', (tester) async {
    await tester.pumpWidget(
      createScreen(() async => throw PantryFailure.connection()),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('pantry-error-state')), findsOneWidget);
    expect(
      find.text('Unable to connect to the server. Please try again.'),
      findsOneWidget,
    );
  });

  testWidgets('shows the generic safe message for backend failures', (
    tester,
  ) async {
    await tester.pumpWidget(
      createScreen(() async => throw PantryFailure.backend()),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('Unable to load your pantry. Please try again.'),
      findsOneWidget,
    );
    expect(find.textContaining('DioException'), findsNothing);
  });

  testWidgets('retry reloads after a failure and shows success', (
    tester,
  ) async {
    var calls = 0;
    Future<List<PantryItem>> load() async {
      calls++;
      if (calls == 1) {
        throw PantryFailure.backend();
      }
      return [pantryItem];
    }

    await tester.pumpWidget(createScreen(load));
    await tester.pumpAndSettle();
    expect(calls, 1);

    await tester.tap(find.byKey(const Key('pantry-retry-button')));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.text('Oats'), findsOneWidget);
    expect(find.byKey(const Key('pantry-error-state')), findsNothing);
  });
}

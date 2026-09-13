import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/features/pantry/data/pantry_repository.dart';
import 'package:mealio/features/pantry/domain/pantry_failure.dart';
import 'package:mealio/features/pantry/domain/pantry_item.dart';
import 'package:mealio/features/pantry/presentation/add_pantry_item_screen.dart';
import 'package:mealio/features/pantry/presentation/pantry_screen.dart';

void main() {
  final oats = Ingredient(
    id: 'ingredient-1',
    name: 'Oats',
    category: 'grain',
    createdAt: DateTime.parse('2026-09-01T10:00:00Z'),
    nutritionValue: null,
  );
  final rice = Ingredient(
    id: 'ingredient-2',
    name: 'Rice',
    category: null,
    createdAt: DateTime.parse('2026-09-01T10:00:00Z'),
    nutritionValue: null,
  );

  Widget createScreen(_FakePantryRepository repository) {
    return ProviderScope(
      overrides: [pantryRepositoryProvider.overrideWithValue(repository)],
      child: const MaterialApp(home: AddPantryItemScreen()),
    );
  }

  Future<void> tapSubmit(WidgetTester tester) async {
    final submit = find.byKey(const Key('add-pantry-submit-button'));
    final formScrollable = tester.state<ScrollableState>(
      find.byType(Scrollable).first,
    );
    formScrollable.position.jumpTo(formScrollable.position.maxScrollExtent);
    await tester.pump();
    await tester.ensureVisible(submit);
    await tester.tap(submit);
  }

  testWidgets('loads initial ingredients and selects exactly one', (
    tester,
  ) async {
    final completer = Completer<List<Ingredient>>();
    final repository = _FakePantryRepository(
      searchHandler: (_) => completer.future,
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pump();
    expect(
      find.byKey(const Key('ingredient-search-loading-indicator')),
      findsOneWidget,
    );

    completer.complete([oats, rice]);
    await tester.pumpAndSettle();
    expect(find.text('Oats'), findsOneWidget);
    expect(find.text('Rice'), findsOneWidget);

    await tester.tap(find.byKey(const Key('ingredient-result-ingredient-1')));
    await tester.pump();
    expect(find.byKey(const Key('selected-ingredient')), findsOneWidget);
  });

  testWidgets(
    'debounces, trims, skips duplicate and maps whitespace to empty',
    (tester) async {
      final repository = _FakePantryRepository(
        searchHandler: (_) async => [oats],
      );
      await tester.pumpWidget(createScreen(repository));
      await tester.pumpAndSettle();
      expect(repository.searches, ['']);

      await tester.enterText(
        find.byKey(const Key('ingredient-search-field')),
        '  oa',
      );
      await tester.pump(const Duration(milliseconds: 200));
      await tester.enterText(
        find.byKey(const Key('ingredient-search-field')),
        '  oats  ',
      );
      await tester.pump(const Duration(milliseconds: 349));
      expect(repository.searches, ['']);
      await tester.pump(const Duration(milliseconds: 1));
      await tester.pump();
      expect(repository.searches, ['', 'oats']);

      await tester.enterText(
        find.byKey(const Key('ingredient-search-field')),
        'oats',
      );
      await tester.pump(const Duration(milliseconds: 400));
      expect(repository.searches, ['', 'oats']);
      await tester.enterText(
        find.byKey(const Key('ingredient-search-field')),
        '   ',
      );
      await tester.pump(const Duration(milliseconds: 400));
      expect(repository.searches, ['', 'oats', '']);
    },
  );

  testWidgets('new search wins over a stale response', (tester) async {
    final initial = Completer<List<Ingredient>>();
    final newer = Completer<List<Ingredient>>();
    final repository = _FakePantryRepository(
      searchHandler: (query) => query.isEmpty ? initial.future : newer.future,
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pump();
    await tester.enterText(
      find.byKey(const Key('ingredient-search-field')),
      'rice',
    );
    await tester.pump(const Duration(milliseconds: 350));
    newer.complete([rice]);
    await tester.pump();
    expect(find.text('Rice'), findsOneWidget);
    initial.complete([oats]);
    await tester.pump();
    expect(find.text('Rice'), findsOneWidget);
    expect(find.text('Oats'), findsNothing);
  });

  testWidgets(
    'query change clears old results before debounce and starts new search after it',
    (tester) async {
      final second = Completer<List<Ingredient>>();
      final repository = _FakePantryRepository(
        searchHandler: (query) =>
            query.isEmpty ? Future.value([oats]) : second.future,
      );
      await tester.pumpWidget(createScreen(repository));
      await tester.pumpAndSettle();

      expect(find.text('Oats'), findsOneWidget);
      expect(repository.searches, ['']);

      await tester.enterText(
        find.byKey(const Key('ingredient-search-field')),
        'rice',
      );
      await tester.pump();

      expect(find.text('Oats'), findsNothing);
      expect(
        find.byKey(const Key('ingredient-search-loading-indicator')),
        findsOneWidget,
      );
      expect(repository.searches, ['']);

      await tester.pump(const Duration(milliseconds: 350));
      expect(repository.searches, ['', 'rice']);

      second.complete([rice]);
      await tester.pump();
      expect(find.text('Rice'), findsOneWidget);
    },
  );

  testWidgets('input change invalidates active search before debounce', (
    tester,
  ) async {
    final first = Completer<List<Ingredient>>();
    final second = Completer<List<Ingredient>>();
    final repository = _FakePantryRepository(
      searchHandler: (query) => query.isEmpty ? first.future : second.future,
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pump();

    await tester.enterText(
      find.byKey(const Key('ingredient-search-field')),
      'rice',
    );
    first.complete([oats]);
    await tester.pump();

    expect(repository.searches, ['']);
    expect(find.text('Oats'), findsNothing);

    await tester.pump(const Duration(milliseconds: 350));
    expect(repository.searches, ['', 'rice']);
    second.complete([rice]);
    await tester.pump();

    expect(find.text('Rice'), findsOneWidget);
    expect(find.text('Oats'), findsNothing);
  });

  testWidgets('A to B to A restarts an invalidated A search', (tester) async {
    final firstA = Completer<List<Ingredient>>();
    final secondA = Completer<List<Ingredient>>();
    var emptyQueryCalls = 0;
    final repository = _FakePantryRepository(
      searchHandler: (query) {
        if (query.isNotEmpty) {
          throw StateError('B must be cancelled before its debounce');
        }
        emptyQueryCalls++;
        return emptyQueryCalls == 1 ? firstA.future : secondA.future;
      },
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pump();

    await tester.enterText(
      find.byKey(const Key('ingredient-search-field')),
      'rice',
    );
    await tester.enterText(
      find.byKey(const Key('ingredient-search-field')),
      '',
    );
    await tester.pump(const Duration(milliseconds: 350));

    expect(repository.searches, ['', '']);
    secondA.complete([rice]);
    await tester.pump();
    expect(find.text('Rice'), findsOneWidget);

    firstA.complete([oats]);
    await tester.pump();
    expect(find.text('Rice'), findsOneWidget);
    expect(find.text('Oats'), findsNothing);
  });

  testWidgets('shows empty, safe error, and retries current query', (
    tester,
  ) async {
    var fail = false;
    final repository = _FakePantryRepository(
      searchHandler: (_) async {
        if (fail) throw PantryFailure.connection();
        return [];
      },
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('ingredient-search-empty')), findsOneWidget);

    fail = true;
    await tester.enterText(
      find.byKey(const Key('ingredient-search-field')),
      'rice',
    );
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pump();
    expect(find.byKey(const Key('ingredient-search-error')), findsOneWidget);
    fail = false;
    await tester.tap(find.byKey(const Key('ingredient-search-retry-button')));
    await tester.pumpAndSettle();
    expect(repository.searches.where((query) => query == 'rice'), hasLength(2));
  });

  testWidgets('invalid ingredient and quantities never create', (tester) async {
    final repository = _FakePantryRepository(
      searchHandler: (_) async => [oats],
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pumpAndSettle();

    for (final value in ['', '0', '-1', 'abc', '1.234', '100000000']) {
      await tester.enterText(
        find.byKey(const Key('pantry-quantity-field')),
        value,
      );
      await tapSubmit(tester);
      await tester.pump();
      expect(repository.createCalls, 0);
    }
    expect(
      find.byKey(const Key('ingredient-validation-error')),
      findsOneWidget,
    );
  });

  testWidgets('first submit shows ingredient and quantity errors together', (
    tester,
  ) async {
    final repository = _FakePantryRepository(
      searchHandler: (_) async => [oats],
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pumpAndSettle();

    await tapSubmit(tester);
    await tester.pump();

    expect(
      find.byKey(const Key('ingredient-validation-error')),
      findsOneWidget,
    );
    expect(find.text('Quantity is required.'), findsOneWidget);
    expect(repository.createCalls, 0);
  });

  testWidgets('failure is safe, preserves form, and retry succeeds once', (
    tester,
  ) async {
    var fail = true;
    final repository = _FakePantryRepository(
      searchHandler: (_) async => [oats],
      createHandler:
          ({required ingredientId, required quantityG, expiresAt}) async {
            if (fail) throw PantryFailure.duplicate();
            return _item(oats);
          },
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('ingredient-result-ingredient-1')));
    await tester.enterText(
      find.byKey(const Key('pantry-quantity-field')),
      '500,25',
    );
    await tapSubmit(tester);
    await tester.pumpAndSettle();
    expect(
      find.text('This ingredient is already in your pantry.'),
      findsOneWidget,
    );
    expect(find.text('500,25'), findsOneWidget);
    expect(find.byKey(const Key('selected-ingredient')), findsOneWidget);

    fail = false;
    await tapSubmit(tester);
    await tester.pump();
    expect(repository.createCalls, 2);
    expect(repository.lastQuantity, '500.25');
  });

  testWidgets('double tap is blocked while create is unresolved', (
    tester,
  ) async {
    final create = Completer<PantryItem>();
    final repository = _FakePantryRepository(
      searchHandler: (_) async => [oats],
      createHandler: ({required ingredientId, required quantityG, expiresAt}) =>
          create.future,
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('ingredient-result-ingredient-1')));
    await tester.enterText(find.byKey(const Key('pantry-quantity-field')), '1');
    await tapSubmit(tester);
    await tapSubmit(tester);
    await tester.pump();
    expect(repository.createCalls, 1);
    expect(
      find.byKey(const Key('add-pantry-loading-indicator')),
      findsOneWidget,
    );
    create.completeError(PantryFailure.createBackend());
    await tester.pumpAndSettle();
  });

  testWidgets('expiry can remain unset or be selected', (tester) async {
    final repository = _FakePantryRepository(
      searchHandler: (_) async => [oats],
      createHandler:
          ({required ingredientId, required quantityG, expiresAt}) async {
            throw PantryFailure.createBackend();
          },
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('ingredient-result-ingredient-1')));
    await tester.enterText(find.byKey(const Key('pantry-quantity-field')), '1');
    await tapSubmit(tester);
    await tester.pumpAndSettle();
    expect(repository.lastExpiry, isNull);

    await tester.tap(find.byKey(const Key('pantry-expiry-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('15'));
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tapSubmit(tester);
    await tester.pumpAndSettle();
    expect(repository.lastExpiry?.isUtc, isTrue);
  });

  testWidgets('reopening expiry keeps the selected calendar day', (
    tester,
  ) async {
    final repository = _FakePantryRepository(
      searchHandler: (_) async => [oats],
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pumpAndSettle();
    await tapSubmit(tester);
    await tester.pump();

    await tester.tap(find.byKey(const Key('pantry-expiry-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('15'));
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('pantry-expiry-button')));
    await tester.pumpAndSettle();
    final calendar = tester.widget<CalendarDatePicker>(
      find.byType(CalendarDatePicker),
    );
    expect(calendar.initialDate, isNotNull);
    expect(calendar.initialDate!.day, 15);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
  });

  testWidgets('dispose during unresolved search is safe', (tester) async {
    final completer = Completer<List<Ingredient>>();
    final repository = _FakePantryRepository(
      searchHandler: (_) => completer.future,
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.pump();
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    completer.complete([oats]);
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('success invalidates pantry and pops to Pantry', (tester) async {
    var pantryLoads = 0;
    final createdItem = _item(oats);
    final repository = _FakePantryRepository(
      pantryHandler: () async {
        pantryLoads++;
        return pantryLoads == 1 ? [] : [createdItem];
      },
      searchHandler: (_) async => [oats],
      createHandler:
          ({required ingredientId, required quantityG, expiresAt}) async =>
              createdItem,
    );
    final router = GoRouter(
      initialLocation: '/pantry',
      routes: [
        GoRoute(path: '/pantry', builder: (_, _) => const PantryScreen()),
        GoRoute(
          path: '/pantry/add',
          builder: (_, _) => const AddPantryItemScreen(),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [pantryRepositoryProvider.overrideWithValue(repository)],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pantry-empty-state')), findsOneWidget);
    await tester.tap(find.byKey(const Key('pantry-add-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('ingredient-result-ingredient-1')));
    await tester.enterText(find.byKey(const Key('pantry-quantity-field')), '1');
    await tapSubmit(tester);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pantry-screen')), findsOneWidget);
    expect(find.byKey(const Key('pantry-item-pantry-1')), findsOneWidget);
    expect(find.text('Oats'), findsOneWidget);
    expect(find.text('1 g'), findsOneWidget);
    expect(pantryLoads, 2);
  });
}

typedef _CreateHandler =
    Future<PantryItem> Function({
      required String ingredientId,
      required String quantityG,
      DateTime? expiresAt,
    });

class _FakePantryRepository implements PantryRepository {
  _FakePantryRepository({
    this.pantryHandler,
    required this.searchHandler,
    this.createHandler,
  });

  final Future<List<PantryItem>> Function()? pantryHandler;
  final Future<List<Ingredient>> Function(String query) searchHandler;
  final _CreateHandler? createHandler;
  final List<String> searches = [];
  int createCalls = 0;
  String? lastQuantity;
  DateTime? lastExpiry;

  @override
  Future<List<PantryItem>> getPantry() =>
      pantryHandler?.call() ?? Future.value([]);

  @override
  Future<List<Ingredient>> searchIngredients({String? search}) {
    final query = search ?? '';
    searches.add(query);
    return searchHandler(query);
  }

  @override
  Future<PantryItem> addPantryItem({
    required String ingredientId,
    required String quantityG,
    DateTime? expiresAt,
  }) {
    createCalls++;
    lastQuantity = quantityG;
    lastExpiry = expiresAt;
    return createHandler?.call(
          ingredientId: ingredientId,
          quantityG: quantityG,
          expiresAt: expiresAt,
        ) ??
        Future.error(PantryFailure.createBackend());
  }

  @override
  Future<PantryItem> updatePantryItem({
    required String pantryItemId,
    required String quantityG,
    DateTime? expiresAt,
  }) => throw UnimplementedError();

  @override
  Future<void> deletePantryItem({required String pantryItemId}) =>
      throw UnimplementedError();
}

PantryItem _item(Ingredient ingredient) => PantryItem(
  id: 'pantry-1',
  userId: 'user-1',
  ingredientId: ingredient.id,
  quantityG: 1,
  expiresAt: null,
  createdAt: DateTime.parse('2026-09-10T10:00:00Z'),
  updatedAt: DateTime.parse('2026-09-10T10:00:00Z'),
  ingredient: ingredient,
);

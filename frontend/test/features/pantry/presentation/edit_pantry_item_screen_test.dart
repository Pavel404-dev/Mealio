import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/features/pantry/data/pantry_repository.dart';
import 'package:mealio/features/pantry/domain/pantry_failure.dart';
import 'package:mealio/features/pantry/domain/pantry_item.dart';
import 'package:mealio/features/pantry/presentation/edit_pantry_item_screen.dart';
import 'package:mealio/features/pantry/presentation/pantry_providers.dart';

void main() {
  final item = _item(expiresAt: DateTime.parse('2026-10-01T00:00:00Z'));

  Widget createScreen(
    _FakePantryRepository repository, {
    PantryItem? pantryItem,
    List<PantryItem>? routeItems,
    bool startAtPantry = false,
  }) {
    final initialItem = pantryItem ?? item;
    return ProviderScope(
      overrides: [pantryRepositoryProvider.overrideWithValue(repository)],
      child: _RoutedEditScreen(
        key: ValueKey('routed-edit-${initialItem.id}'),
        initialItemId: initialItem.id,
        items: routeItems ?? [initialItem],
        startAtPantry: startAtPantry,
      ),
    );
  }

  Future<void> tapSave(WidgetTester tester) async {
    final button = find.byKey(const Key('edit-pantry-save-button'));
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pump();
  }

  Future<void> tapDelete(WidgetTester tester) async {
    final button = find.byKey(const Key('edit-pantry-delete-button'));
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pump();
  }

  testWidgets(
    'shows read-only ingredient and exact initial quantity and expiry',
    (tester) async {
      final repository = _FakePantryRepository();
      await tester.pumpWidget(createScreen(repository));

      expect(find.byKey(const Key('edit-pantry-ingredient')), findsOneWidget);
      expect(find.text('Oats'), findsOneWidget);
      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const Key('edit-pantry-quantity-field')),
            )
            .controller
            ?.text,
        '250.5',
      );
      expect(find.text('2026-10-01'), findsOneWidget);
      expect(
        find.byKey(const Key('edit-pantry-expiry-clear-button')),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'valid save preserves decimal input and expiry in repository arguments',
    (tester) async {
      final repository = _FakePantryRepository(
        updateHandler: (_, _, _) async => item,
      );
      await tester.pumpWidget(createScreen(repository));
      await tester.enterText(
        find.byKey(const Key('edit-pantry-quantity-field')),
        '500,25',
      );
      await tapSave(tester);
      await tester.pumpAndSettle();

      expect(repository.updateCalls, 1);
      expect(repository.lastPantryItemId, 'pantry-1');
      expect(repository.lastQuantity, '500.25');
      expect(repository.lastExpiry, DateTime.utc(2026, 10, 1));
      expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
      expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('invalid quantities never update', (tester) async {
    final repository = _FakePantryRepository();
    await tester.pumpWidget(createScreen(repository));
    await tester.enterText(
      find.byKey(const Key('edit-pantry-quantity-field')),
      '0',
    );
    await tapSave(tester);

    expect(find.text('Quantity must be greater than zero.'), findsOneWidget);
    expect(repository.updateCalls, 0);
  });

  testWidgets('clearing expiry submits an explicit null', (tester) async {
    final repository = _FakePantryRepository(
      updateHandler: (_, _, _) async => item,
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.tap(find.byKey(const Key('edit-pantry-expiry-clear-button')));
    await tapSave(tester);
    await tester.pumpAndSettle();

    expect(repository.updateCalls, 1);
    expect(repository.lastExpiry, isNull);
    expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'update failure preserves the form and one retry sends one new request',
    (tester) async {
      var fail = true;
      final repository = _FakePantryRepository(
        updateHandler: (_, _, _) async {
          if (fail) throw PantryFailure.updateBackend();
          return item;
        },
      );
      await tester.pumpWidget(createScreen(repository));
      await tester.enterText(
        find.byKey(const Key('edit-pantry-quantity-field')),
        '500.25',
      );
      await tapSave(tester);
      expect(
        find.byKey(const Key('edit-pantry-error-message')),
        findsOneWidget,
      );
      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const Key('edit-pantry-quantity-field')),
            )
            .controller
            ?.text,
        '500.25',
      );

      fail = false;
      await tapSave(tester);
      await tester.pumpAndSettle();
      expect(repository.updateCalls, 2);
      expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
      expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'unresolved update accepts only one submit and blocks competing actions',
    (tester) async {
      final completer = Completer<PantryItem>();
      final repository = _FakePantryRepository(
        updateHandler: (_, _, _) => completer.future,
      );
      await tester.pumpWidget(createScreen(repository));
      await tapSave(tester);
      await tapSave(tester);
      await tapDelete(tester);

      expect(repository.updateCalls, 1);
      expect(repository.deleteCalls, 0);
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('edit-pantry-save-button')),
            )
            .onPressed,
        isNull,
      );
      expect(
        tester
            .widget<IconButton>(
              find.byKey(const Key('edit-pantry-back-button')),
            )
            .onPressed,
        isNull,
      );

      completer.complete(item);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('system Back cannot leave a pushed unresolved update', (
    tester,
  ) async {
    final completer = Completer<PantryItem>();
    final repository = _FakePantryRepository(
      updateHandler: (_, _, _) => completer.future,
    );
    await tester.pumpWidget(createScreen(repository, startAtPantry: true));
    await tester.pumpAndSettle();
    final pantryContext = tester.element(
      find.byKey(const Key('fake-pantry-destination')),
    );
    final router = GoRouter.of(pantryContext);
    router.push('/pantry/pantry-1/edit');
    await tester.pumpAndSettle();
    expect(router.canPop(), isTrue);
    await tapSave(tester);

    await tester.binding.handlePopRoute();
    await tester.pump();

    expect(find.byKey(const Key('edit-pantry-item-screen')), findsOneWidget);
    expect(repository.updateCalls, 1);

    completer.complete(item);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('quantity-only save preserves the original expiry instant', (
    tester,
  ) async {
    final expiresAt = DateTime.parse('2026-10-01T18:30:00Z');
    final repository = _FakePantryRepository(
      updateHandler: (_, _, _) async => item,
    );
    await tester.pumpWidget(
      createScreen(repository, pantryItem: _item(expiresAt: expiresAt)),
    );
    await tester.enterText(
      find.byKey(const Key('edit-pantry-quantity-field')),
      '500',
    );
    await tapSave(tester);
    await tester.pumpAndSettle();

    expect(repository.lastExpiry, expiresAt);
    expect(
      repository.lastExpiry?.toIso8601String(),
      '2026-10-01T18:30:00.000Z',
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('cancelling the date picker preserves the original instant', (
    tester,
  ) async {
    final expiresAt = DateTime.parse('2026-10-01T18:30:00Z');
    final repository = _FakePantryRepository(
      updateHandler: (_, _, _) async => item,
    );
    await tester.pumpWidget(
      createScreen(repository, pantryItem: _item(expiresAt: expiresAt)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('edit-pantry-expiry-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    await tapSave(tester);
    await tester.pumpAndSettle();

    expect(repository.lastExpiry, expiresAt);
    expect(tester.takeException(), isNull);
  });

  testWidgets('selected expiry is submitted at UTC midnight', (tester) async {
    final repository = _FakePantryRepository(
      updateHandler: (_, _, _) async => item,
    );
    await tester.pumpWidget(createScreen(repository));
    await tester.tap(find.byKey(const Key('edit-pantry-expiry-button')));
    await tester.pumpAndSettle();
    await _selectDate(tester, DateTime(2026, 11, 5));
    await tapSave(tester);
    await tester.pumpAndSettle();

    expect(repository.lastExpiry, DateTime.utc(2026, 11, 5));
    expect(tester.takeException(), isNull);
  });

  testWidgets('date picker accepts existing expiry outside its default range', (
    tester,
  ) async {
    final now = DateTime.now();
    for (final expiresAt in [
      DateTime.utc(now.year - 15, 6, 15, 18, 30),
      DateTime.utc(now.year + 25, 6, 15, 18, 30),
    ]) {
      final repository = _FakePantryRepository(
        updateHandler: (_, _, _) async => item,
      );
      await tester.pumpWidget(
        createScreen(
          repository,
          pantryItem: _item(
            id: 'pantry-expiry-${expiresAt.year}',
            expiresAt: expiresAt,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('edit-pantry-expiry-button')));
      await tester.pumpAndSettle();
      expect(find.byType(CalendarDatePicker), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(find.text(_dateLabel(expiresAt)), findsOneWidget);

      await tester.tap(find.byKey(const Key('edit-pantry-expiry-button')));
      await tester.pumpAndSettle();
      await _selectDate(tester, DateTime(now.year, 6, 16));
      await tapSave(tester);
      await tester.pumpAndSettle();

      expect(repository.lastExpiry, DateTime.utc(now.year, 6, 16));
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('delete confirmation cancel never deletes and unlocks actions', (
    tester,
  ) async {
    final repository = _FakePantryRepository();
    await tester.pumpWidget(createScreen(repository));
    await tapDelete(tester);
    expect(
      find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const Key('edit-pantry-delete-cancel-button')));
    await tester.pumpAndSettle();

    expect(repository.deleteCalls, 0);
    expect(
      tester
          .widget<FilledButton>(
            find.byKey(const Key('edit-pantry-save-button')),
          )
          .onPressed,
      isNotNull,
    );
    expect(
      tester
          .widget<TextButton>(
            find.byKey(const Key('edit-pantry-delete-button')),
          )
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('system Back dismisses delete confirmation and unlocks actions', (
    tester,
  ) async {
    final repository = _FakePantryRepository();
    await tester.pumpWidget(createScreen(repository));
    await tapDelete(tester);

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
      findsNothing,
    );
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(
            find.byKey(const Key('edit-pantry-save-button')),
          )
          .onPressed,
      isNotNull,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('barrier dismisses delete confirmation and unlocks actions', (
    tester,
  ) async {
    final repository = _FakePantryRepository();
    await tester.pumpWidget(createScreen(repository));
    await tapDelete(tester);

    await tester.tapAt(const Offset(8, 8));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
      findsNothing,
    );
    expect(repository.deleteCalls, 0);
    expect(
      tester
          .widget<FilledButton>(
            find.byKey(const Key('edit-pantry-save-button')),
          )
          .onPressed,
      isNotNull,
    );
    expect(
      tester
          .widget<TextButton>(
            find.byKey(const Key('edit-pantry-delete-button')),
          )
          .onPressed,
      isNotNull,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('two Delete taps before a frame open only one confirmation', (
    tester,
  ) async {
    final repository = _FakePantryRepository();
    await tester.pumpWidget(createScreen(repository));
    final button = find.byKey(const Key('edit-pantry-delete-button'));
    await tester.ensureVisible(button);
    final deleteButton = tester.widget<TextButton>(button);
    deleteButton.onPressed!.call();
    deleteButton.onPressed!.call();
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
      findsOneWidget,
    );
    expect(repository.deleteCalls, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('double confirm performs one DELETE without popping edit route', (
    tester,
  ) async {
    final delete = Completer<void>();
    final repository = _FakePantryRepository(
      deleteHandler: (_) => delete.future,
    );
    await tester.pumpWidget(createScreen(repository));
    await tapDelete(tester);
    final confirm = find.byKey(const Key('edit-pantry-delete-confirm-button'));
    final confirmButton = tester.widget<FilledButton>(confirm);
    confirmButton.onPressed!.call();
    confirmButton.onPressed!.call();
    await tester.pump();

    expect(repository.deleteCalls, 1);
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsOneWidget);

    delete.complete();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
    expect(
      find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('delete confirmation and mutation prevent a competing save', (
    tester,
  ) async {
    final delete = Completer<void>();
    final repository = _FakePantryRepository(
      deleteHandler: (_) => delete.future,
    );
    await tester.pumpWidget(createScreen(repository));
    await tapDelete(tester);

    expect(
      tester
          .widget<FilledButton>(
            find.byKey(const Key('edit-pantry-save-button')),
          )
          .onPressed,
      isNull,
    );
    await tester.tap(
      find.byKey(const Key('edit-pantry-save-button')),
      warnIfMissed: false,
    );
    await tester.pump();
    expect(repository.updateCalls, 0);

    await tester.tap(
      find.byKey(const Key('edit-pantry-delete-confirm-button')),
    );
    await tester.pump();
    expect(repository.deleteCalls, 1);
    expect(repository.updateCalls, 0);

    await tester.tap(
      find.byKey(const Key('edit-pantry-save-button')),
      warnIfMissed: false,
    );
    await tester.pump();
    expect(repository.updateCalls, 0);

    delete.complete();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('system Back cannot leave a pushed unresolved delete', (
    tester,
  ) async {
    final delete = Completer<void>();
    final repository = _FakePantryRepository(
      deleteHandler: (_) => delete.future,
    );
    await tester.pumpWidget(createScreen(repository, startAtPantry: true));
    await tester.pumpAndSettle();
    final pantryContext = tester.element(
      find.byKey(const Key('fake-pantry-destination')),
    );
    final router = GoRouter.of(pantryContext);
    router.push('/pantry/pantry-1/edit');
    await tester.pumpAndSettle();
    expect(router.canPop(), isTrue);
    await tapDelete(tester);
    await tester.tap(
      find.byKey(const Key('edit-pantry-delete-confirm-button')),
    );
    await tester.pump();
    expect(repository.deleteCalls, 1);

    await tester.binding.handlePopRoute();
    await tester.pump();

    expect(find.byKey(const Key('edit-pantry-item-screen')), findsOneWidget);
    expect(find.byKey(const Key('fake-pantry-destination')), findsNothing);
    expect(repository.deleteCalls, 1);

    delete.complete();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('confirmed delete invokes exactly one request', (tester) async {
    final repository = _FakePantryRepository(deleteHandler: (_) async {});
    await tester.pumpWidget(createScreen(repository));
    await tapDelete(tester);
    await tester.tap(
      find.byKey(const Key('edit-pantry-delete-confirm-button')),
    );
    await tester.pumpAndSettle();

    expect(repository.deleteCalls, 1);
    expect(repository.lastPantryItemId, 'pantry-1');
    expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
    expect(
      find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('delete failure stays on screen and permits retry', (
    tester,
  ) async {
    var fail = true;
    final repository = _FakePantryRepository(
      deleteHandler: (_) async {
        if (fail) throw PantryFailure.deleteBackend();
      },
    );
    await tester.pumpWidget(createScreen(repository));
    await tapDelete(tester);
    await tester.tap(
      find.byKey(const Key('edit-pantry-delete-confirm-button')),
    );
    await tester.pump();
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsOneWidget);
    expect(find.byKey(const Key('edit-pantry-error-message')), findsOneWidget);

    fail = false;
    await tapDelete(tester);
    await tester.tap(
      find.byKey(const Key('edit-pantry-delete-confirm-button')),
    );
    await tester.pumpAndSettle();
    expect(repository.deleteCalls, 2);
    expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('success invalidates pantry list and returns to Pantry', (
    tester,
  ) async {
    var pantryLoads = 0;
    final repository = _FakePantryRepository(
      pantryHandler: () async {
        pantryLoads++;
        return [item];
      },
      updateHandler: (_, _, _) async => item,
    );
    final router = GoRouter(
      initialLocation: '/pantry',
      routes: [
        GoRoute(path: '/pantry', builder: (_, _) => const _PantryDestination()),
        GoRoute(
          path: '/pantry/edit',
          builder: (_, _) => EditPantryItemScreen(
            key: const ValueKey('edit-pantry-item-pantry-1'),
            pantryItem: item,
          ),
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
    final context = tester.element(
      find.byKey(const Key('fake-pantry-destination')),
    );
    GoRouter.of(context).push('/pantry/edit');
    await tester.pumpAndSettle();
    await tapSave(tester);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
    expect(
      find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
      findsNothing,
    );
    expect(repository.updateCalls, 1);
    expect(pantryLoads, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'successful delete invalidates pantry list and returns to Pantry',
    (tester) async {
      var pantryLoads = 0;
      final repository = _FakePantryRepository(
        pantryHandler: () async {
          pantryLoads++;
          return [item];
        },
        deleteHandler: (_) async {},
      );
      final router = GoRouter(
        initialLocation: '/pantry',
        routes: [
          GoRoute(
            path: '/pantry',
            builder: (_, _) => const _PantryDestination(),
          ),
          GoRoute(
            path: '/pantry/edit',
            builder: (_, _) => EditPantryItemScreen(
              key: const ValueKey('edit-pantry-item-pantry-1'),
              pantryItem: item,
            ),
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
      final context = tester.element(
        find.byKey(const Key('fake-pantry-destination')),
      );
      GoRouter.of(context).push('/pantry/edit');
      await tester.pumpAndSettle();
      await tapDelete(tester);
      await tester.tap(
        find.byKey(const Key('edit-pantry-delete-confirm-button')),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('fake-pantry-destination')), findsOneWidget);
      expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
      expect(
        find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
        findsNothing,
      );
      expect(repository.deleteCalls, 1);
      expect(pantryLoads, 2);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('disposing during unresolved update or delete is safe', (
    tester,
  ) async {
    final update = Completer<PantryItem>();
    final repository = _FakePantryRepository(
      updateHandler: (_, _, _) => update.future,
    );
    await tester.pumpWidget(createScreen(repository));
    await tapSave(tester);
    await tester.pumpWidget(const SizedBox());
    update.complete(item);
    await tester.pump();
    expect(tester.takeException(), isNull);

    final delete = Completer<void>();
    final deleteRepository = _FakePantryRepository(
      deleteHandler: (_) => delete.future,
    );
    await tester.pumpWidget(createScreen(deleteRepository));
    await tapDelete(tester);
    await tester.tap(
      find.byKey(const Key('edit-pantry-delete-confirm-button')),
    );
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    delete.complete();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}

class _PantryDestination extends ConsumerWidget {
  const _PantryDestination();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(pantryItemsProvider);
    return const Scaffold(key: Key('fake-pantry-destination'));
  }
}

class _RoutedEditScreen extends StatefulWidget {
  const _RoutedEditScreen({
    required this.initialItemId,
    required this.items,
    required this.startAtPantry,
    super.key,
  });

  final String initialItemId;
  final List<PantryItem> items;
  final bool startAtPantry;

  @override
  State<_RoutedEditScreen> createState() => _RoutedEditScreenState();
}

class _RoutedEditScreenState extends State<_RoutedEditScreen> {
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    final itemsById = {for (final item in widget.items) item.id: item};
    _router = GoRouter(
      initialLocation: widget.startAtPantry
          ? '/pantry'
          : '/pantry/${widget.initialItemId}/edit',
      routes: [
        GoRoute(path: '/pantry', builder: (_, _) => const _PantryDestination()),
        GoRoute(
          path: '/pantry/:pantryItemId/edit',
          builder: (_, state) {
            final pantryItem = itemsById[state.pathParameters['pantryItemId']];
            if (pantryItem == null) {
              return const _PantryDestination();
            }
            return EditPantryItemScreen(pantryItem: pantryItem);
          },
        ),
      ],
    );
  }

  @override
  void dispose() {
    _router.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      MaterialApp.router(routerConfig: _router);
}

Future<void> _selectDate(WidgetTester tester, DateTime selected) async {
  final picker = tester.widget<CalendarDatePicker>(
    find.byType(CalendarDatePicker),
  );
  picker.onDateChanged(selected);
  await tester.pump();
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

String _dateLabel(DateTime date) {
  final utcDate = date.toUtc();
  return '${utcDate.year.toString().padLeft(4, '0')}-'
      '${utcDate.month.toString().padLeft(2, '0')}-'
      '${utcDate.day.toString().padLeft(2, '0')}';
}

typedef _UpdateHandler = Future<PantryItem> Function(String, String, DateTime?);
typedef _DeleteHandler = Future<void> Function(String);

class _FakePantryRepository implements PantryRepository {
  _FakePantryRepository({
    this.pantryHandler,
    this.updateHandler,
    this.deleteHandler,
  });

  final Future<List<PantryItem>> Function()? pantryHandler;
  final _UpdateHandler? updateHandler;
  final _DeleteHandler? deleteHandler;
  int updateCalls = 0;
  int deleteCalls = 0;
  String? lastPantryItemId;
  String? lastQuantity;
  DateTime? lastExpiry;

  @override
  Future<List<PantryItem>> getPantry() =>
      pantryHandler?.call() ?? Future.value([]);

  @override
  Future<PantryItem> updatePantryItem({
    required String pantryItemId,
    required String quantityG,
    DateTime? expiresAt,
  }) {
    updateCalls++;
    lastPantryItemId = pantryItemId;
    lastQuantity = quantityG;
    lastExpiry = expiresAt;
    return updateHandler?.call(pantryItemId, quantityG, expiresAt) ??
        Future.value(_item(expiresAt: expiresAt));
  }

  @override
  Future<void> deletePantryItem({required String pantryItemId}) {
    deleteCalls++;
    lastPantryItemId = pantryItemId;
    return deleteHandler?.call(pantryItemId) ?? Future.value();
  }

  @override
  Future<PantryItem> addPantryItem({
    required String ingredientId,
    required String quantityG,
    DateTime? expiresAt,
  }) => throw UnimplementedError();

  @override
  Future<List<Ingredient>> searchIngredients({String? search}) =>
      Future.value([]);
}

PantryItem _item({
  String id = 'pantry-1',
  String ingredientId = 'ingredient-1',
  String ingredientName = 'Oats',
  double quantityG = 250.5,
  DateTime? expiresAt,
}) => PantryItem(
  id: id,
  userId: 'user-1',
  ingredientId: ingredientId,
  quantityG: quantityG,
  expiresAt: expiresAt,
  createdAt: DateTime.parse('2026-09-10T10:00:00Z'),
  updatedAt: DateTime.parse('2026-09-10T10:00:00Z'),
  ingredient: Ingredient(
    id: ingredientId,
    name: ingredientName,
    category: 'grain',
    createdAt: DateTime.parse('2026-09-01T10:00:00Z'),
    nutritionValue: null,
  ),
);

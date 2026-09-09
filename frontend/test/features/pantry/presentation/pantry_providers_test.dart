import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/pantry/data/pantry_repository.dart';
import 'package:mealio/features/pantry/domain/pantry_failure.dart';
import 'package:mealio/features/pantry/domain/pantry_item.dart';
import 'package:mealio/features/pantry/presentation/pantry_providers.dart';

void main() {
  ProviderContainer createContainer(_StubPantryRepository repository) {
    final container = ProviderContainer(
      overrides: [pantryRepositoryProvider.overrideWithValue(repository)],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('production provider loads from repository exactly once', () async {
    final repository = _StubPantryRepository(() async => []);
    final container = createContainer(repository);
    final subscription = container.listen(
      pantryItemsProvider,
      (previous, next) {},
      fireImmediately: true,
    );
    addTearDown(subscription.close);

    final items = await container.read(pantryItemsProvider.future);

    expect(items, isEmpty);
    expect(repository.calls, 1);
    expect(
      container.read(pantryItemsProvider),
      isA<AsyncData<List<PantryItem>>>(),
    );
  });

  test(
    'production provider does not auto-retry and invalidation loads once',
    () async {
      var shouldFail = true;
      final repository = _StubPantryRepository(() async {
        if (shouldFail) {
          throw PantryFailure.backend();
        }
        return [];
      });
      final container = createContainer(repository);
      final subscription = container.listen(
        pantryItemsProvider,
        (previous, next) {},
        fireImmediately: true,
      );
      addTearDown(subscription.close);

      await expectLater(
        container.read(pantryItemsProvider.future),
        throwsA(isA<PantryFailure>()),
      );
      expect(repository.calls, 1);

      await Future<void>.delayed(const Duration(milliseconds: 500));
      expect(repository.calls, 1);

      shouldFail = false;
      container.invalidate(pantryItemsProvider);
      final items = await container.read(pantryItemsProvider.future);

      expect(repository.calls, 2);
      expect(items, isEmpty);
      final state = container.read(pantryItemsProvider);
      expect(state, isA<AsyncData<List<PantryItem>>>());
      expect(state.value, isEmpty);
    },
  );
}

class _StubPantryRepository implements PantryRepository {
  _StubPantryRepository(this._handler);

  final Future<List<PantryItem>> Function() _handler;
  int calls = 0;

  @override
  Future<List<PantryItem>> getPantry() {
    calls++;
    return _handler();
  }
}

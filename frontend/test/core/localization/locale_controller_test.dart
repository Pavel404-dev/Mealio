import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/localization/locale_controller.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';

import '../../helpers/locale_test_fakes.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  ProviderContainer containerFor(MemoryLocaleStorage storage) {
    final container = ProviderContainer(
      overrides: [localeStorageProvider.overrideWithValue(storage)],
    );
    addTearDown(container.dispose);
    return container;
  }

  for (final code in ['en', 'ru', 'uk', 'sk']) {
    test(
      '$code override is immediate, persisted and restored on restart',
      () async {
        final storage = MemoryLocaleStorage();
        final first = containerFor(storage);
        final controller = first.read(localeControllerProvider.notifier);
        await controller.restored;
        final saved = controller.setLocale(Locale(code));
        expect(first.read(localeControllerProvider), Locale(code));
        expect(await saved, isTrue);
        final second = containerFor(storage);
        await second.read(localeControllerProvider.notifier).restored;
        expect(second.read(localeControllerProvider), Locale(code));
      },
    );
  }

  test(
    'returning to system deletes the override and survives restart',
    () async {
      final storage = MemoryLocaleStorage('ru');
      final first = containerFor(storage);
      final controller = first.read(localeControllerProvider.notifier);
      await controller.restored;
      expect(first.read(localeControllerProvider), const Locale('ru'));
      expect(await controller.setLocale(null), isTrue);
      expect(storage.value, isNull);
      final second = containerFor(storage);
      await second.read(localeControllerProvider.notifier).restored;
      expect(second.read(localeControllerProvider), isNull);
    },
  );

  test(
    'unsupported or unreadable stored value uses system and remains usable',
    () async {
      for (final storage in [
        MemoryLocaleStorage('unsupported'),
        MemoryLocaleStorage()..failRead = true,
      ]) {
        final container = containerFor(storage);
        final controller = container.read(localeControllerProvider.notifier);
        await controller.restored;
        expect(container.read(localeControllerProvider), isNull);
        expect(await controller.setLocale(const Locale('sk')), isTrue);
        expect(container.read(localeControllerProvider), const Locale('sk'));
      }
    },
  );

  test(
    'a delayed restore cannot overwrite a new choice or system reset',
    () async {
      for (final choice in [const Locale('uk'), null]) {
        final storage = MemoryLocaleStorage()
          ..pendingRead = Completer<String?>();
        final container = containerFor(storage);
        final controller = container.read(localeControllerProvider.notifier);
        await controller.setLocale(choice);
        storage.pendingRead!.complete('ru');
        await controller.restored;
        expect(container.read(localeControllerProvider), choice);
      }
    },
  );

  test('writes are serialized and last choice survives a restart', () async {
    final storage = MemoryLocaleStorage()..pendingWrite = Completer<void>();
    final container = containerFor(storage);
    final controller = container.read(localeControllerProvider.notifier);
    await controller.restored;
    final first = controller.setLocale(const Locale('ru'));
    final second = controller.setLocale(const Locale('sk'));
    await Future<void>.delayed(Duration.zero);
    expect(storage.writes, ['ru']);
    expect(container.read(localeControllerProvider), const Locale('sk'));
    storage.pendingWrite!.complete();
    expect(await first, isTrue);
    expect(await second, isTrue);
    expect(storage.writes, ['ru', 'sk']);
    expect(storage.value, 'sk');
  });

  test(
    'failed write is reported, keeps current locale and allows retry',
    () async {
      final storage = MemoryLocaleStorage()..failWrite = true;
      final container = containerFor(storage);
      final controller = container.read(localeControllerProvider.notifier);
      await controller.restored;
      expect(await controller.setLocale(const Locale('ru')), isFalse);
      expect(container.read(localeControllerProvider), const Locale('ru'));
      storage.failWrite = false;
      expect(await controller.setLocale(const Locale('ru')), isTrue);
      expect(storage.value, 'ru');
    },
  );

  test('locale storage and credential cleanup are independent', () async {
    FlutterSecureStorage.setMockInitialValues({
      accessTokenStorageKey: 'synthetic-test-access',
      refreshTokenStorageKey: 'synthetic-test-refresh',
    });
    const secure = FlutterSecureStorage();
    final locale = LocaleStorage(secure);
    await locale.write('uk');
    expect(
      await secure.read(key: accessTokenStorageKey),
      'synthetic-test-access',
    );
    await SecureStorageService(secure).deleteTokenPair();
    expect(await locale.read(), 'uk');
    await locale.write(null);
    expect(await locale.read(), isNull);
  });
}

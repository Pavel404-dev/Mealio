import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/pantry_repository.dart';
import '../domain/pantry_item.dart';

final pantryItemsProvider = FutureProvider.autoDispose<List<PantryItem>>(
  (ref) => ref.watch(pantryRepositoryProvider).getPantry(),
  retry: (retryCount, error) => null,
);

import 'dart:async';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:mealio/core/localization/locale_controller.dart';

class MemoryLocaleStorage extends LocaleStorage {
  MemoryLocaleStorage([this.value]) : super(const FlutterSecureStorage());

  String? value;
  bool failRead = false;
  bool failWrite = false;
  Completer<String?>? pendingRead;
  Completer<void>? pendingWrite;
  final writes = <String?>[];

  @override
  Future<String?> read() async {
    if (failRead) throw StateError('Synthetic preference read failure');
    return pendingRead == null ? value : await pendingRead!.future;
  }

  @override
  Future<void> write(String? languageCode) async {
    writes.add(languageCode);
    await pendingWrite?.future;
    if (failWrite) throw StateError('Synthetic preference write failure');
    value = languageCode;
  }
}

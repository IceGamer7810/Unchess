import 'package:flutter/material.dart';

ThemeData buildUnchessTheme() {
  const background = Color(0xFFF4EBDD);
  const surface = Color(0xFFE6D7C3);
  const accent = Color(0xFF6A4428);
  const text = Color(0xFF2B2118);

  return ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: accent,
      brightness: Brightness.light,
      background: background,
      surface: surface,
    ),
    scaffoldBackgroundColor: background,
    textTheme: const TextTheme(
      headlineMedium: TextStyle(
        fontSize: 30,
        fontWeight: FontWeight.w700,
        color: text,
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        color: text,
      ),
      bodyMedium: TextStyle(
        fontSize: 14,
        color: text,
      ),
    ),
    useMaterial3: true,
  );
}


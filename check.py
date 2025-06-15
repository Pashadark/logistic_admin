try:
    import bootstrap5
    print("✅ Bootstrap5 успешно установлен!")
    print(f"Версия: {bootstrap5.__version__}")
except ImportError:
    print("❌ Bootstrap5 не установлен!")
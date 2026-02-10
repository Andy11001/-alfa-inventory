
def get_availability_word(model_name):
    if not model_name: 
        return "dostępny"
        
    m = model_name.upper().strip()

    # Logika dla DS (Marka męska - "Ten DS")
    if "DS" in m or m.startswith("DS"):
        return "dostępny"
    
    # Logika dla Alfa Romeo (Marka żeńska - "Ta Alfa")
    # Domyślnie: "dostępna"
    # Wyjątki: Rzeczowniki męskie kończące się na spółgłoskę (np. Junior, Spider)
    # Ale nie akronimy czy liczby (np. 159, 147, GT, GTV, 4C - "Ta Alfa 159", "Ta Alfa GT")
    
    # Bierzemy ostatnie słowo nazwy modelu
    parts = m.split()
    last_word = parts[-1] if parts else m
    
    # 1. Sprawdzamy czy ostatnie słowo kończy się na samogłoskę (A, E, I, O, U, Y)
    # Giulia (A), Stelvio (O), Tonale (E), Brera (A), MiTo (O) -> Żeńskie (Ta Alfa...)
    if last_word[-1] in ['A', 'E', 'I', 'O', 'U', 'Y']:
        return "dostępna"
        
    # 2. Sprawdzamy czy to krótki akronim lub liczba (GT, GTV, 159, 147, 4C, 8C)
    # Zazwyczaj traktowane jako żeńskie przez domyślne "Ta Alfa"
    # Heurystyka: Długość <= 3 znaki LUB same cyfry
    if len(last_word) <= 3 or last_word.isdigit():
        return "dostępna"
        
    # 3. Jeśli zostało coś dłuższego niż 3 znaki i kończy się na spółgłoskę
    # Np. JUNIOR (R), SPIDER (R), CROSSWAGON (N) -> Męskie
    return "dostępny"

# Test cases
test_models = [
    "Alfa Romeo Giulia",    # Oczekiwane: dostępna
    "Alfa Romeo Stelvio",   # Oczekiwane: dostępna
    "Alfa Romeo Tonale",    # Oczekiwane: dostępna
    "Alfa Romeo Junior",    # Oczekiwane: dostępna (Ta Alfa)
    "Alfa Romeo Spider",    # Oczekiwane: dostępna (Ta Alfa)
    "Alfa Romeo Brera",     # Oczekiwane: dostępna
    "Alfa Romeo 159",       # Oczekiwane: dostępna
    "Alfa Romeo 147",       # Oczekiwane: dostępna
    "Alfa Romeo GT",        # Oczekiwane: dostępna
    "Alfa Romeo GTV",       # Oczekiwane: dostępna
    "Alfa Romeo MiTo",      # Oczekiwane: dostępna
    "Alfa Romeo 4C",        # Oczekiwane: dostępna
    "Alfa Romeo 8C",        # Oczekiwane: dostępna
    "DS 3",                 # Oczekiwane: dostępny
    "DS 4",                 # Oczekiwane: dostępny
    "DS 7",                 # Oczekiwane: dostępny
    "DS 9",                 # Oczekiwane: dostępny
    "DS N°4",               # Oczekiwane: dostępny
    "Alfa Romeo Brennero",  # (Hipotetyczny - O) -> dostępna
    "Alfa Romeo Milano",    # (Hipotetyczny - O) -> dostępna
    "Alfa Romeo Furiosa",   # (Hipotetyczny - A) -> dostępna
    "Alfa Romeo King",      # (Hipotetyczny - G) -> dostępna
]

print(f"{'MODEL':<25} | {'WYNIK':<10} | {'OCZEKIWANE':<10}")
print("-" * 50)
for params in test_models:
    res = get_availability_word(params)
    print(f"{params:<25} | {res:<10}")

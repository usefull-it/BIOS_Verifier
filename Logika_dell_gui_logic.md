# Logika tabeli i komunikatów (dell_gui_logic.py)

Ten plik nie rysuje okna i nie łączy się z Dellem. Ustalają to dwa pozostałe pliki. Tutaj są zasady samej tabeli: kolejność kolumn, które wiersze zostały zaznaczone, jaki link skopiować i jaki tekst pokazać na pasku stanu po pobieraniu.

## Kolumny

Stała kolejność danych w każdym wierszu:

1. Model
2. Wersja BIOS
3. Data wydania
4. Zmiana
5. Poprzednia weryfikacja
6. Ważność
7. Link

Ta kolejność opisuje, w jakiej kolejności wartości są wkładane do wiersza. Kolejność widoczna na ekranie może być inna, jeśli użytkownik przeciągnął nagłówki. Nazwy kolumn przy tym się nie zmieniają. Nie da się tą drogą dodać ani usunąć kolumny.

Wartości wiersza są układane dokładnie według stałej listy powyżej. Brakujące pole w danych wiersza jest błędem przygotowania danych, a nie pustą komórką do samodzielnego uzupełnienia.

## Kolejność kolumn na ekranie

Ustawienie jest w pliku `gui-ustawienia.json`, w tym samym folderze co program. W pliku jest jedna lista: kolejność nazw kolumn.

Odczyt:

- Brak pliku daje układ domyślny, czyli stałą kolejność z listy wyżej.
- Plik nie do odczytu albo o złym formacie też daje układ domyślny. Program nie pokazuje wtedy osobnego błędu.
- Z zapisanej listy brane są tylko prawdziwe nazwy znanych kolumn. Powtórzenia są pomijane. Nieznane nazwy są pomijane.
- Znana kolumna, której w zapisie zabrakło, jest doklejana na końcu. Dzięki temu nowa kolumna dodana w przyszłej wersji programu nie znika tylko dlatego, że stary plik ustawień jej nie wymienia.

Zapis nadpisuje cały plik ustawień i zostawia w nim wyłącznie aktualną kolejność kolumn.

Przesunięcie kolumny działa tak: złapana kolumna jest wyjmowana ze swojego miejsca i wstawiana tuż przed kolumnę, na którą ją upuszczono. Reszta kolumn zostaje we wzajemnej kolejności. Upuszczenie kolumny na samą siebie albo podanie nazwy spoza listy nic nie zmienia.

Numer kolumny wskazany przez tabelę (`#1`, `#2`, …) jest zamieniany na pozycję licząc od zera: `#1` to pierwsza widoczna kolumna. Numer poza zakresem albo tekst bez znaku `#` jest odrzucany. Okno traktuje takie odrzucenie jako „nie zmieniaj kolejności”.

## Zaznaczenie wierszy

Zaznaczenie jest liczone według kolejności wierszy na ekranie, od góry do dołu, a nie według kolejności kliknięć. Dzięki temu pobieranie i kopiowanie idą w tej samej kolejności, w jakiej użytkownik widzi tabelę.

Do pobrania zaznaczonych wierszy:

- Pusta tabela daje komunikat „Najpierw sprawdź wersje BIOS.” Nic nie jest pobierane.
- Tabela z wierszami, ale bez zaznaczenia, daje „Zaznacz wiersze, które chcesz pobrać.”
- Przy poprawnym zaznaczeniu zwracane są dokładnie te wiersze, w kolejności z tabeli. Dalsze filtrowanie adresów robi już logika BIOS, nie ten plik. Ten plik nie odrzuca wiersza za to, że zmiana nie jest „nową wersją”.

## Kopiowanie linku

Brany jest jeden wiersz: pierwszy z zaznaczonych w kolejności tabeli. Okno samo wybiera ten pierwszy indeks i przekazuje go tutaj.

- Brak zaznaczenia albo indeks spoza tabeli: „Zaznacz wiersz, którego link chcesz skopiować.”
- Zaznaczony wiersz ma pusty link: „Zaznaczony wiersz nie ma linku.”
- Link jest: tekst „Skopiowano link.” i sam adres do wklejenia w schowek. Wklejenia do schowka dokonuje okno, nie ten plik.

## Komunikaty po pobieraniu

Tekst paska stanu składa się z czterech liczb i informacji, który przycisk był użyty.

- Nie było wierszy do rozpatrzenia: „Najpierw sprawdź wersje BIOS.”
- Nic nie zaplanowano i nie było błędów, a pobieranie dotyczyło tylko nowych wersji: „Brak nowych wersji do pobrania.”
- Nic nie zaplanowano i nie było błędów, a pobieranie dotyczyło zaznaczonych wierszy: „Brak plików do pobrania.”
- Zapisano dokładnie jeden plik i nie było błędów: „Pobrano 1 plik do pobrane-bios.”
- Zapisano więcej niż jeden plik i nie było błędów: „Pobrano X plików do pobrane-bios.”
- Był choć jeden błąd: „Pobrano X plików, błędy: Y.” Przy jednym zapisanym pliku słowo brzmi „plik”, nie „plików”.

Liczba błędów obejmuje zarówno adresy odrzucone przed pobraniem, jak i pliki, których nie udało się ściągnąć. Ten plik nie rozróżnia tych dwóch przyczyn w tekście. Pokazuje jedną sumę.

Zero zapisanych plików przy błędach też daje komunikat z liczbą błędów, na przykład „Pobrano 0 plików, błędy: 2.”, a nie komunikat o braku plików. Komunikat o braku plików pojawia się wyłącznie wtedy, gdy plan był pusty i błędów nie było.

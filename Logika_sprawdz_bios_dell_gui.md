# Logika okna aplikacji (sprawdz_bios_dell_gui.py)

Ten plik to okno programu „Weryfikator wersji BIOS Dell”. Nie pobiera sam katalogów Della i nie porównuje wersji. Od tego jest plik z logiką BIOS. Ten plik pokazuje tabelę, przyciski i pasek stanu oraz pilnuje, żeby dłuższe czynności (łączenie z internetem, zapis plików) nie zamrażały okna.

Okno ma na starcie rozmiar 1100 na 480 pikseli. Tytuł: „Weryfikator wersji BIOS Dell”.

## Co widać na ekranie, od góry

- Przewijana część z tabelą wyników.
- Podpowiedź, jak wpisać nazwę modelu (tekst pochodzi z logiki BIOS).
- Pole tekstowe i przyciski:
  - „Dodaj model”
  - „Usuń zaznaczony model”
  - „Kopiuj link”
  - „Pobierz zaznaczone elementy”
  - „Pobierz wszystkie nowe wersje”
  - „Sprawdź aktualizacje wersji BIOS”
- Na samym dole pasek stanu. Na starcie pokazuje „Gotowy”.

Przyciski są zawsze przy dole okna, także gdy okno jest niskie. Tabela jest nad nimi i ma własny pionowy suwak. Gdy całe okno jest za niskie, da się przewinąć treść kółkiem myszy.

## Pliki, z których okno korzysta

Wszystkie leżą w tym samym folderze co program.

- `bios-stan.json` — ostatni wynik sprawdzenia wersji. Okno tylko podaje ścieżkę do tego pliku. Treść zapisuje logika BIOS.
- `gui-ustawienia.json` — zapamiętana kolejność kolumn tabeli.
- `modele-uzytkownika.json` — modele dopisane przez użytkownika oraz modele wbudowane, które użytkownik ukrył.
- Folder `pobrane-bios` — tu trafiają pobrane pliki BIOS.

## Tabela

Kolumny, od lewej w układzie domyślnym:

1. Model
2. Wersja BIOS
3. Data wydania
4. Zmiana
5. Poprzednia weryfikacja
6. Ważność
7. Link

Kolumna „Link” jest szersza od pozostałych. Można zaznaczyć wiele wierszy naraz. Kolejność kolumn da się zmienić przeciągnięciem nagłówka. Nowy układ jest zapisywany i przy następnym uruchomieniu program go odtwarza.

### Przeciąganie kolumn

- Program reaguje tylko na naciśnięcie nagłówka kolumny, nie na kliknięcie wiersza.
- Po puszczeniu przycisku myszy kolumna, którą złapano, wskakuje na miejsce kolumny, nad którą puszczono przycisk.
- Puszczenie myszy poza szerokością tabeli nic nie zmienia.
- Upuszczenie kolumny na samą siebie nic nie zmienia i nic nie zapisuje.
- Po rzeczywistej zmianie kolejności tabela od razu się przebudowuje, a nowa kolejność trafia do `gui-ustawienia.json`.

### Kółko myszy

- Kółko przewija całe okno.
- Wyjątek: gdy kursor jest nad tabelą albo jej suwakiem i tabela ma jeszcze własne wiersze do przewinięcia, kółko przewija wiersze tabeli, a nie całe okno.
- Gdy wszystkie wiersze tabeli już mieszczą się na ekranie, kółko znowu przewija całe okno.

## Zasada „program jest zajęty”

W trakcie sprawdzania, dodawania modelu i pobierania plików program blokuje pięć przycisków: sprawdzenie, oba pobierania, dodanie modelu i usunięcie modelu. Drugie kliknięcie w tym czasie jest ignorowane. Pasek stanu pokazuje, co trwa. Po zakończeniu przyciski wracają do działania.

Kopiowanie linku i zmiana kolejności kolumn nie są blokowane.

Długie czynności idą obok okna, w tle. Okno dostaje wynik dopiero, gdy czynność się skończy, i samo odświeża tabelę oraz komunikaty. Dzięki temu okno nie przestaje reagować w trakcie pobierania.

## Sprawdzenie aktualizacji

Przycisk: „Sprawdź aktualizacje wersji BIOS”.

1. Jeśli program jest zajęty, nic się nie dzieje.
2. Program czyta listę modeli użytkownika.
3. Gdy plik `modele-uzytkownika.json` jest uszkodzony, pokazuje błąd „Nie można odczytać modele-uzytkownika.json. Plik nie został zmieniony.” Sprawdzenie się nie zaczyna. Plik zostaje nietknięty.
4. W przeciwnym razie składa listę do sprawdzenia: modele wbudowane plus modele dopisane przez użytkownika, bez modeli świadomie usuniętych z listy.
5. Blokuje przyciski, na pasku ustawia „Pobieranie…” i w tle prosi logikę BIOS o żywe sprawdzenie.
6. Gdy sprawdzenie skończy się nieoczekiwanym błędem, program traktuje to jak błąd całego sprawdzenia i pokazuje treść błędu.

### Co dzieje się z wynikiem

- Przy błędzie, przez który nie da się pokazać tabeli (na przykład uszkodzony `bios-stan.json` albo brak połączenia z katalogiem Della), pasek stanu i okno błędu pokazują ten komunikat. Stara tabela zostaje bez zmian.
- Przy zwykłym wyniku tabela jest czyszczona i wypełniana od nowa.
- Gdy każdy model został odczytany, pasek pokazuje „Gotowe — wszystkie modele odczytane.”
- Gdy część modeli ma błąd, pasek pokazuje „Zakończono z błędami niektórych modeli.” Te modele i tak są w tabeli, a opis błędu jest w kolumnie „Zmiana”.

## Dodanie modelu

Przycisk: „Dodaj model”. Tekst bierze z pola obok przycisku.

1. Jeśli program jest zajęty, nic się nie dzieje.
2. Pusta nazwa (albo sama spacja, albo samo słowo „Dell”) daje błąd „Pusta nazwa modelu.” plus podpowiedź formatu. Nic nie jest zapisywane.
3. Uszkodzony plik `modele-uzytkownika.json` daje ten sam komunikat co przy sprawdzaniu. Plik nie jest zmieniany.
4. Program blokuje przyciski i na pasku ustawia „Szukanie modelu w katalogu Dell…”.
5. W tle szuka wpisanej nazwy w aktualnym katalogu Della.

### Gdy wyszukiwanie się nie uda

Pasek i okno błędu pokazują przyczynę (brak programu do rozpakowania katalogów, brak połączenia, model nieznaleziony albo inny błąd). Przyciski wracają. Lista modeli się nie zmienia.

### Gdy model został znaleziony

1. Program sprawdza, czy ta nazwa jest już na bieżącej liście (wbudowane i dopisane, bez ukrytych).
2. Jeśli jest, pokazuje informację „Ten model jest już na liście.” i nic nie zapisuje.
3. Jeśli model był wcześniej ukryty, zdejmuje go z listy ukrytych. Wraca więc do sprawdzeń.
4. Jeśli to jeden z modeli wbudowanych w program, nie dopisuje go drugi raz do pliku użytkownika. Wystarczy, że nie jest już ukryty.
5. Jeśli to nowy model spoza listy wbudowanej, dopisuje go do `modele-uzytkownika.json` razem z numerami systemowymi znalezionymi w katalogu Della.
6. Zapisuje plik. Gdy zapis się nie uda, pokazuje treść błędu i nie uruchamia sprawdzenia.
7. Po udanym zapisie od razu uruchamia pełne sprawdzenie aktualnej listy, tak jak przycisk „Sprawdź aktualizacje wersji BIOS”. Pasek wraca do tekstu „Pobieranie…”. Pole tekstowe nie jest czyszczone przez samo dodanie.

## Usunięcie modelu

Przycisk: „Usuń zaznaczony model”.

1. Jeśli program jest zajęty, nic się nie dzieje.
2. Bez zaznaczenia pasek pokazuje „Zaznacz model do usunięcia.”
3. Z zaznaczonych wierszy zbiera nazwy modeli, bez powtórzeń i z zachowaniem kolejności w tabeli.
4. Gdy z zaznaczenia nie da się odczytać żadnej nazwy, pasek znowu pokazuje „Zaznacz model do usunięcia.”
5. Uszkodzony plik `modele-uzytkownika.json` blokuje usunięcie tym samym komunikatem co przy sprawdzaniu. Plik nie jest zmieniany.
6. Program prosi logikę BIOS o zdjęcie tych nazw z listy:
   - model dopisany przez użytkownika znika z jego listy,
   - model wbudowany zostaje w programie, ale trafia na listę ukrytych, więc kolejne sprawdzenia go pomijają.
7. Gdy zapis pliku się nie uda, pokazuje błąd. Tabela zostaje bez zmian.
8. Po udanym zapisie usuwa z tabeli wiersze tych modeli i na pasku ustawia „Usunięto model z listy sprawdzenia.” Nie łączy się wtedy z internetem i nie przebudowuje pozostałych wierszy.

Można zaznaczyć kilka wierszy. Wszystkie wskazane modele są usuwane za jednym razem.

## Kopiowanie linku

Przycisk „Kopiuj link” albo skrót Ctrl+C, gdy tabela ma fokus.

1. Bierze pod uwagę pierwszy zaznaczony wiersz w kolejności wyświetlania, a nie kolejności klikania.
2. Gdy nic nie zaznaczono, pasek pokazuje „Zaznacz wiersz, którego link chcesz skopiować.”
3. Gdy wiersz nie ma linku, pasek pokazuje „Zaznaczony wiersz nie ma linku.”
4. Gdy link jest, trafia do schowka, a pasek pokazuje „Skopiowano link.”

Kopiowanie nie pobiera pliku. Kopiuje tylko adres z kolumny „Link”.

## Pobieranie zaznaczonych wierszy

Przycisk: „Pobierz zaznaczone elementy”.

Pobiera pliki dla zaznaczonych wierszy niezależnie od tego, co jest w kolumnie „Zmiana”. Może to być nowa wersja, brak zmian albo pierwsza kontrola, byle wiersz miał poprawny adres pliku Dell.

1. Jeśli program jest zajęty, nic się nie dzieje.
2. Gdy tabela jest pusta, pasek pokazuje „Najpierw sprawdź wersje BIOS.”
3. Gdy nic nie zaznaczono, pasek pokazuje „Zaznacz wiersze, które chcesz pobrać.”
4. W pozostałych przypadkach blokuje przyciski, ustawia „Pobieranie plików BIOS…” i w tle pobiera tylko zaznaczone wiersze.

## Pobieranie wszystkich nowych wersji

Przycisk: „Pobierz wszystkie nowe wersje”.

1. Jeśli program jest zajęty, nic się nie dzieje.
2. Gdy tabela jest pusta, pasek pokazuje „Najpierw sprawdź wersje BIOS.” Pobieranie się nie zaczyna.
3. W przeciwnym razie bierze wszystkie wiersze ostatniego sprawdzenia, ale do pobrania kwalifikuje tylko te, w których kolumna „Zmiana” zaczyna się od słów „nowa wersja”.
4. Blokuje przyciski i ustawia „Pobieranie plików BIOS…”.

## Wspólne zakończenie pobierania

Pliki mają trafić do folderu `pobrane-bios` obok programu. Program najpierw układa plan (które adresy są bezpieczne), potem pobiera pliki z planu.

Po zakończeniu pasek pokazuje jeden z komunikatów:

- „Brak nowych wersji do pobrania.” — przy pobieraniu wszystkich nowych, gdy żaden wiersz nie był nową wersją.
- „Brak plików do pobrania.” — przy pobieraniu zaznaczonych, gdy z zaznaczenia nie został żaden poprawny plik.
- „Pobrano 1 plik do pobrane-bios.” — gdy zapisano dokładnie jeden plik i nie było błędów.
- „Pobrano X plików do pobrane-bios.” — gdy zapisano więcej niż jeden plik i nie było błędów.
- „Pobrano X plików, błędy: Y.” albo „Pobrano 1 plik, błędy: Y.” — gdy część się udała, a część została odrzucona albo nie doszła z sieci.

Gdy pobieranie przerwie nieoczekiwany błąd, na pasku pojawia się treść tego błędu, bez osobnego okna. Przyciski zawsze wracają do działania po zakończeniu, także po błędzie.

## Uruchomienie

Otwarcie tego pliku jako programu tworzy okno i zostawia je otwarte, aż użytkownik je zamknie.

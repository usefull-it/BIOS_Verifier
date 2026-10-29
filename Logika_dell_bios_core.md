# Logika sprawdzania BIOS Dell (dell_bios_core.py)

Ten plik jest silnikiem programu. Nie rysuje okna. Ustala, skąd wziąć dane, który pakiet BIOS jest najnowszy, co zapisać na dysku i które pliki wolno pobrać.

Źródłem danych jest publiczny katalog Della w formacie używanym przez OpenManage:

- główny indeks komputerów PC: plik `CatalogIndexPC.cab` pod adresem `https://downloads.dell.com/catalog/CatalogIndexPC.cab`,
- dla każdego modelu osobny katalog CAB wskazany przez ten indeks.

Katalogi są spakowane. Do rozpakowania potrzebny jest program `cabextract` dostępny w systemie. Bez niego sprawdzenie i dodawanie modelu kończą się komunikatem „Brak programu cabextract, wymaganego do rozpakowania katalogu CAB.”

Pobrania idą na serwer Della z nagłówkiem przeglądarki, żeby serwer przyjął połączenie jak zwykłą wizytę ze strony.

Pliki tymczasowe lądują w katalogu tymczasowym systemu, w podfolderze `DellBiosVerifier` o jednorazowej nazwie. Po zakończeniu czynności ten podfolder jest usuwany, także gdy wystąpił błąd.

## Modele wbudowane

Program zna od razu te modele i ich numery systemowe Della (`systemID`):

- Dell Latitude 5401 — 0918
- Dell Latitude 5420 — 0A20, 0A40
- Dell Latitude 5430 — 0B04, 0B05
- Dell Latitude 5440 — 0C00, 0C01, 0D0B
- Dell Latitude 5520 — 0A21, 0A41
- Dell Precision 3561 — 0A68
- Dell Precision 5560 — 0A62

Jeden model może mieć kilka numerów systemowych, bo Dell publikuje dla niego więcej niż jeden wariant. Własne modele użytkownika nie są dopisywane do tej stałej listy. Trafiają do pliku `modele-uzytkownika.json`.

## Pliki na dysku

Obok programu powstają dwa pliki JSON.

### bios-stan.json

Pamięta ostatnie udane sprawdzenie każdego modelu: wersję, datę wydania, ważność, link i datę sprawdzenia (pole „kiedy sprawdzono”, w pliku zapisane jako data dzisiejsza w formacie rok-miesiąc-dzień).

Odczyt pliku:

- Brak pliku oznacza pierwszy start. Program tworzy wtedy pusty stan i pracuje dalej.
- Poprawny plik ma obiekt z polem listy modeli. Pusta lista modeli jest traktowana jak brak historii.
- Plik nie do odczytu, pusty w złym formacie albo z listą modeli w złym kształcie jest uznawany za uszkodzony. Program wtedy nic nie nadpisuje i zwraca komunikat „Nie można odczytać bios-stan.json. Plik nie został zmieniony.”

Zapis obejmuje tylko pięć pól na model: wersję, datę wydania, ważność, link i datę sprawdzenia. Inne ewentualne dopiski w starym pliku nie są przenoszone.

Stan jest zapisywany tylko wtedy, gdy w danym sprawdzeniu udało się odczytać co najmniej jeden model. Modele z błędem nie kasują wcześniejszego, udanego wpisu. Modele, których tym razem w ogóle nie sprawdzano, zostają w pliku bez zmian.

### modele-uzytkownika.json

Ma dwie listy:

- modele dopisane przez użytkownika (nazwa i numery systemowe),
- modele wykluczone, czyli ukryte ze sprawdzania.

Odczyt:

- Brak pliku oznacza brak dopisków i brak ukrytych modeli.
- Każdy model musi mieć niepustą nazwę i co najmniej jeden niepusty numer systemowy.
- Lista ukrytych, jeśli jest, może zawierać tylko niepuste nazwy. Brak tej listy w starszym pliku oznacza „nikt nie jest ukryty”.
- Jakikolwiek błąd formatu oznacza plik uszkodzony. Program go nie poprawia i nie nadpisuje, dopóki użytkownik nie doprowadzi do poprawnego zapisu inną, udaną czynnością. Komunikat dla okna: „Nie można odczytać modele-uzytkownika.json. Plik nie został zmieniony.”

Zapis zawsze zapisuje obie listy naraz.

## Kogo program sprawdza

Lista do sprawdzenia powstaje tak:

1. Najpierw modele wbudowane, w stałej kolejności.
2. Potem modele użytkownika, których nazwa nie powtarza już wbudowanej.
3. Na końcu odpadają nazwy z listy ukrytych.

Ukrycie modelu wbudowanego nie usuwa go z programu. Powrót takiego modelu na listę polega na zdjęciu go z listy ukrytych, bez dopisywania kopii do modeli użytkownika.

## Szukanie modelu po nazwie

Podpowiedź pokazywana w oknie:

„Podaj angielską nazwę z pola Display katalogu Dell, bez obowiązkowego słowa Dell na początku. Przykład: Latitude 7450. Wielkość liter nie ma znaczenia. Aplikacja dopasuje całą nazwę i zbierze wszystkie numery systemID o tym display name.”

Przygotowanie wpisu użytkownika:

- Zbędne spacje są ściągane do pojedynczych.
- Słowo „Dell” na początku jest pomijane.
- Porównanie ignoruje wielkość liter.

Pusta nazwa po tym oczyszczeniu daje błąd „Pusta nazwa modelu.” plus podpowiedź.

Żywe szukanie, używane przy „Dodaj model”:

1. Sprawdza, czy jest program `cabextract`.
2. Pobiera główny indeks PC i go rozpakowuje.
3. W indeksie dla każdego modelu składa nazwę z marki nadrzędnej i nazwy wyświetlanej. Przykład: marka „Latitude” i nazwa „5410” dają „Latitude 5410”. Gdy nazwa wyświetlana już zawiera markę, nie jest dublowana.
4. Porównuje złożoną nazwę z wpisem użytkownika.
5. Zbiera wszystkie numery systemowe pasujące do tej samej nazwy i sortuje je.
6. Kanoniczna nazwa zapisywana w programie zawsze zaczyna się od „Dell ”, na przykład „Dell Latitude 7450”.

Gdy nic nie pasuje, komunikat brzmi „Nie znaleziono modelu „…”. ” plus podpowiedź. W cudzysłowie jest wpis użytkownika po ściągnięciu zbędnych spacji, jeszcze przed zmianą na samą formę porównawczą.

Błąd pobrania indeksu: „Nie udało się pobrać katalogu Dell: CatalogIndexPC.cab”. Błąd rozpakowania: „Nie udało się rozpakować katalogu Dell.” Błąd treści XML: „Katalog Dell ma nieczytelny XML.”

## Pełne sprawdzenie

Kolejność:

1. Odczyt albo utworzenie `bios-stan.json`. Uszkodzony plik kończy sprawdzenie od razu, bez łączenia z siecią.
2. Sprawdzenie, czy jest `cabextract`.
3. Pobranie i rozpakowanie głównego indeksu.
4. Dla każdego modelu z listy — osobny wynik, opisany niżej.
5. Zapis stanu, jeśli choć jeden model się udał.
6. Usunięcie plików tymczasowych.

Wynik całego sprawdzenia:

- kod powodzenia, gdy każdy model został odczytany,
- kod błędu, gdy choć jeden model się nie udał, ale tabela i tak zawiera wiersze,
- osobny komunikat blokujący, gdy nie da się nawet zacząć (uszkodzony stan albo indeks nie do pobrania). Wtedy lista wierszy jest pusta.

Awaria indeksu przerywa całe sprawdzenie. Awaria jednego modelu nie przerywa pozostałych.

## Wynik jednego modelu

Dla każdego numeru systemowego modelu:

1. W indeksie szuka tego numeru i ścieżki do katalogu danej platformy.
2. Brak numerów albo brak ścieżki daje „błąd: brak modelu w katalogu”.
3. Pobiera katalog tej platformy. Niepowodzenie daje „błąd: nie pobrano katalogu modelu”.
4. Rozpakowuje go. Nieczytelny XML albo nieudane rozpakowanie daje „błąd: nieczytelny katalog modelu”.
5. Z katalogu wybiera najnowszy pakiet BIOS.

Gdy model ma kilka numerów, program powtarza to dla każdego. Błąd jednego numeru odrzuca cały model. Nie składa wersji „w połowie”.

### Który pakiet BIOS jest najnowszy

Z katalogu platformy brane są tylko składniki, których kategoria i typ to BIOS.

- Brak takiego składnika: „błąd: brak pakietu BIOS”.
- Data wydania musi mieć postać angielską, na przykład „October 2, 2026”. Inna data, pusta data albo niemożliwy dzień (na przykład 31 kwietnia) daje „błąd: nieczytelna data wydania” dla całego katalogu, nawet jeśli inne pakiety mają dobrą datę.

Spośród poprawnych pakietów wygrywa:

1. późniejsza data wydania,
2. przy tej samej dacie — wyższy numer wersji Della,
3. przy tej samej dacie i tym samym numerze — późniejsza w porządku alfabetycznym ścieżka pliku.

Porównanie numeru wersji:

- Gdy obie strony składają się wyłącznie z liczb rozdzielonych kropkami, porównanie jest liczbowe. „1.9” jest starsze niż „1.10”.
- Gdy numer zawiera litery, porównanie jest zwykłym porównaniem tekstu.
- Jednakowy zapis oznacza brak różnicy.

Ważność z katalogu Della jest tłumaczona tak:

- Urgent → Krytyczna
- Recommended → Zalecana
- Optional → Opcjonalna
- cokolwiek innego → nieznana

Link do pliku powstaje przez doklejenie ścieżki z katalogu do `https://downloads.dell.com/`. Ukośniki na początku ścieżki są pomijane, żeby adres się nie zdublował.

### Co widać, gdy model ma kilka wariantów

- Wersja: jeśli wszystkie warianty mają ten sam numer, w tabeli jest jeden numer. Jeśli numery się różnią, w tabeli jest lista „numer systemowy: wersja”, posortowana po numerze systemowym i rozdzielona średnikiem.
- Data wydania, ważność i link biorą się z jednego zwycięskiego wariantu, wyłonionego tą samą zasadą co najnowszy pakiet: najpierw data, potem numer wersji, potem ścieżka pliku.

### Wiersz tabeli po udanym odczycie

- Model — nazwa z listy.
- Wersja BIOS — numer albo zestaw numerów opisany wyżej.
- Data wydania — data zwycięskiego pakietu w formacie rok-miesiąc-dzień.
- Zmiana — porównanie z poprzednim stanem, opisane niżej.
- Poprzednia weryfikacja — data poprzedniego udanego sprawdzenia albo puste pole, gdy modelu nie było w stanie.
- Ważność — przetłumaczona ważność zwycięskiego pakietu.
- Link — adres pliku zwycięskiego pakietu.

### Wiersz tabeli po błędzie modelu

Wersja, data, ważność i link są puste. W kolumnie „Zmiana” jest treść błędu. Poprzednia data weryfikacji zostaje, jeśli model był już kiedyś zapisany. Poprzedni udany wpis w `bios-stan.json` nie jest przy tym kasowany.

## Kolumna „Zmiana”

Porównanie dotyczy wyłącznie numeru wersji zapisanego przy poprzednim sprawdzeniu, nie daty wydania.

- Brak poprzedniej wersji (pierwszy zapis tego modelu): „pierwsza kontrola”.
- Ten sam numer co poprzednio: „bez zmian”.
- Inny numer: „nowa wersja (poprzednio …)” z poprzednim numerem w nawiasie.

Puste pole poprzedniej wersji jest traktowane jak brak historii, czyli „pierwsza kontrola”, a nie jak zmiana.

## Plan pobierania plików

Program nie pobiera wszystkiego, co jest w tabeli, zanim nie ułoży planu.

Dwa tryby:

- Tylko nowe wersje. Do planu wchodzą wiersze, których „Zmiana” zaczyna się od „nowa wersja”. „pierwsza kontrola” i „bez zmian” są pomijane. Błędy modeli też są pomijane, bo ich tekst nie zaczyna się od tych słów.
- Zaznaczone wiersze. Warunku „nowa wersja” nie ma. Liczy się każdy przekazany wiersz.

Dla wiersza, który wszedł do rozpatrzenia, nazwa pliku jest wycinana z linku.

Link jest przyjęty tylko wtedy, gdy spełnia wszystkie warunki:

- zaczyna się od `https://downloads.dell.com/`,
- nazwa pliku jest ostatnim członem adresu, bez końcowego ukośnika i bez części po znaku zapytania,
- nazwa nie jest kropką ani dwiema kropkami,
- nazwa zawiera wyłącznie litery, cyfry, kropkę, podkreślenie i myślnik.

Inny link trafia na listę odrzuconych. Odrzucenie jest liczone jako błąd pobierania, nawet jeśli plik w ogóle nie był ściągany. Dzięki temu program nie zapisze pliku spoza Della i nie przyjmie nazwy, która mogłaby wyjść poza folder docelowy.

## Zapis pobranych plików

Folder docelowy jest tworzony, jeśli go nie ma. Dla każdej pozycji planu program prosi o pobranie adresu do pliku o ustalonej nazwie w tym folderze.

- Udane pobranie dodaje pełną ścieżkę zapisanego pliku do listy udanych.
- Błąd sieci albo zapisu dodaje samą nazwę pliku do listy błędów i przechodzi do kolejnej pozycji. Jedna porażka nie przerywa reszty.

Plik o tej samej nazwie, jeśli już leży w folderze, zostaje nadpisany nową treścią.

## Scalanie i usuwanie modeli

Scalanie dwóch list (wbudowanej i użytkownika) dokleja z drugiej listy tylko te nazwy, których jeszcze nie ma. Przy powtórzonej nazwie zostaje wcześniejszy wpis, razem z jego numerami systemowymi.

Sprawdzenie „czy model już jest na liście” porównuje pełną nazwę znak po znaku, łącznie z wielkością liter. „Dell Latitude 7450” i inny zapis tej samej frazy są różnymi nazwami.

Usuwanie z listy działa zależnie od pochodzenia nazwy:

- model tylko użytkownika znika z jego listy,
- model wbudowany zostaje dopisany do listy ukrytych, jeśli jeszcze tam nie był,
- nazwa, która jest i wbudowana, i na liście użytkownika, jest ukrywana oraz zdejmowana z listy użytkownika.

Powtórne ukrycie tej samej nazwy nie dubluje wpisu na liście ukrytych.

// The strings v1.1.0 added to the integration's dialogs, for the languages
// under out/: node tools/i18n/i18n_delta_v110.js
//
// It writes them into out/<code>.backend.json at the places the English
// source has them. Run i18n_check.js and i18n_build.js afterwards.
const fs = require("fs");
const path = require("path");

const dir = __dirname;
// venueMenu, currencyMenu (both with their emoji), venueTitle, venueDesc,
// search, newTitle, newDesc, convert, help, helpHold, currencyTitle,
// currencyDesc, noRate
const T = {
  cs: {
    venueTitle: "Změnit kotaci",
    venueDesc: "{name} je veden jako {symbol}. Vyhledejte jej znovu - podle ISIN nebo názvu - a vyberte jinou burzu nebo zdroj.",
    search: "Hledat",
    newTitle: "Vyberte novou kotaci",
    newDesc: "Nalezeno pro \"{query}\". {name} je odteď veden tam; jeho název, nákupy, alarmy a senzory zůstávají. Nákupy, prodeje a cenové alarmy se nepřepočítávají - v jiné měně platí jejich čísla v ní. Změní-li se měna, dlouhodobé statistiky jeho senzorů začnou znovu.",
    convert: "Přepočítat na {base}",
    help: "Pro kotaci v jiné měně: vše se zobrazuje v {base}, podle referenčního kurzu ECB.",
    helpHold: "To, co držíte, se pak také zadává v {base}.",
    currencyTitle: "Měna",
    currencyDesc: "{name} je kotován v {quoted}. Po zapnutí se vše zobrazuje v {base}: cena podle referenčního kurzu ECB daného dne, každý bod grafu podle kurzu svého dne. Není to cena, za kterou se obchoduje v {base}, a změna zahrnuje i změnu měny. Již zadané nákupy, prodeje a cenové alarmy se nepřepočítávají - jejich čísla od té chvíle platí jako {base}. Změní-li se měna, dlouhodobé statistiky jeho senzorů začnou znovu.",
    noRate: "Pro měnu této kotace ECB nezveřejňuje referenční kurz, proto ji nelze přepočítat.",
  },
  da: {
    venueTitle: "Skift notering",
    venueDesc: "{name} føres som {symbol}. Søg efter det igen - med ISIN eller navn - for at vælge en anden børs eller kilde.",
    search: "Søg",
    newTitle: "Vælg den nye notering",
    newDesc: "Fundet for \"{query}\". {name} føres der fra nu af; navn, køb, alarmer og sensorer bliver. Køb, salg og kursalarmer omregnes ikke - i en anden valuta gælder deres tal som den. Skifter valutaen, begynder langtidsstatistikken for sensorerne forfra.",
    convert: "Omregn til {base}",
    help: "For en notering i en anden valuta: alt vises i {base}, til ECB's referencekurs.",
    helpHold: "Din beholdning indtastes så også i {base}.",
    currencyTitle: "Valuta",
    currencyDesc: "{name} noteres i {quoted}. Slået til vises alt i {base} i stedet: kursen til ECB's referencekurs for dagen, hvert punkt i grafen til kursen for sin egen dag. Det er ikke den kurs, det handles til i {base}, og ændringen indeholder valutaens. Køb, salg og kursalarmer, der allerede er indtastet, omregnes ikke - deres tal gælder fra da af som {base}. Skifter valutaen, begynder langtidsstatistikken for sensorerne forfra.",
    noRate: "ECB offentliggør ingen referencekurs for denne noterings valuta, så den kan ikke omregnes.",
  },
  es: {
    venueTitle: "Cambiar la cotización",
    venueDesc: "{name} figura como {symbol}. Búscalo de nuevo - por su ISIN o su nombre - para elegir otra bolsa o fuente.",
    search: "Buscar",
    newTitle: "Elegir la nueva cotización",
    newDesc: "Encontrado para \"{query}\". {name} cotiza allí desde ahora; su nombre, sus compras, sus alertas y sus sensores se mantienen. Las compras, las ventas y las alertas de precio no se convierten: en otra moneda sus cifras cuentan como esa. Si cambia la moneda, las estadísticas a largo plazo de sus sensores empiezan de nuevo.",
    convert: "Convertir a {base}",
    help: "Para una cotización en otra moneda: todo se muestra en {base}, al tipo de referencia del BCE.",
    helpHold: "Lo que tienes se introduce entonces también en {base}.",
    currencyTitle: "Moneda",
    currencyDesc: "{name} cotiza en {quoted}. Activado, todo se muestra en {base}: el precio al tipo de referencia del BCE del día, cada punto del gráfico al tipo de su propio día. No es el precio al que se negocia en {base}, y la variación incluye la de la moneda. Las compras, ventas y alertas de precio ya introducidas no se convierten: sus cifras cuentan como {base} desde entonces. Si cambia la moneda, las estadísticas a largo plazo de sus sensores empiezan de nuevo.",
    noRate: "El BCE no publica un tipo de referencia para la moneda de esta cotización, por lo que no se puede convertir.",
  },
  fi: {
    venueTitle: "Vaihda listaus",
    venueDesc: "{name} on listattu symbolilla {symbol}. Hae se uudelleen - ISIN-koodilla tai nimellä - ja valitse toinen pörssi tai lähde.",
    search: "Haku",
    newTitle: "Valitse uusi listaus",
    newDesc: "Löytyi haulla \"{query}\". {name} noteerataan tästä lähtien siellä; nimi, ostot, hälytykset ja anturit säilyvät. Ostoja, myyntejä ja hintahälytyksiä ei muunneta - toisessa valuutassa niiden luvut ovat sitä valuuttaa. Jos valuutta vaihtuu, anturien pitkän aikavälin tilastot alkavat alusta.",
    convert: "Muunna valuuttaan {base}",
    help: "Toisessa valuutassa olevalle listaukselle: kaikki näytetään valuutassa {base}, EKP:n viitekurssilla.",
    helpHold: "Omistus syötetään silloin myös valuutassa {base}.",
    currencyTitle: "Valuutta",
    currencyDesc: "{name} noteerataan valuutassa {quoted}. Kun tämä on päällä, kaikki näytetään valuutassa {base}: kurssi EKP:n päivän viitekurssilla, kaavion jokainen piste oman päivänsä kurssilla. Se ei ole kurssi, jolla sillä käydään kauppaa valuutassa {base}, ja muutos sisältää valuutan muutoksen. Jo syötettyjä ostoja, myyntejä ja hintahälytyksiä ei muunneta - niiden luvut ovat siitä lähtien valuuttaa {base}. Jos valuutta vaihtuu, anturien pitkän aikavälin tilastot alkavat alusta.",
    noRate: "EKP ei julkaise viitekurssia tämän listauksen valuutalle, joten sitä ei voi muuntaa.",
  },
  fr: {
    venueTitle: "Changer de cotation",
    venueDesc: "{name} est coté sous {symbol}. Recherchez-le à nouveau - par son ISIN ou son nom - pour choisir une autre bourse ou source.",
    search: "Recherche",
    newTitle: "Choisir la nouvelle cotation",
    newDesc: "Résultats pour « {query} ». {name} y est coté désormais ; son nom, ses achats, ses alertes et ses capteurs restent. Les achats, les ventes et les alertes de cours ne sont pas convertis : dans une autre devise, leurs chiffres valent dans celle-ci. Si la devise change, les statistiques à long terme de ses capteurs repartent de zéro.",
    convert: "Convertir en {base}",
    help: "Pour une cotation dans une autre devise : tout est affiché en {base}, au taux de référence de la BCE.",
    helpHold: "Ce que vous détenez se saisit alors aussi en {base}.",
    currencyTitle: "Devise",
    currencyDesc: "{name} est coté en {quoted}. Activé, tout est affiché en {base} : le cours au taux de référence de la BCE du jour, chaque point du graphique au taux de son propre jour. Ce n'est pas le cours auquel il se négocie en {base}, et la variation inclut celle de la devise. Les achats, ventes et alertes de cours déjà saisis ne sont pas convertis : leurs chiffres valent en {base} dès lors. Si la devise change, les statistiques à long terme de ses capteurs repartent de zéro.",
    noRate: "La BCE ne publie pas de taux de référence pour la devise de cette cotation ; elle ne peut donc pas être convertie.",
  },
  it: {
    venueTitle: "Cambia quotazione",
    venueDesc: "{name} è quotato come {symbol}. Cercalo di nuovo - per ISIN o per nome - per scegliere un'altra borsa o fonte.",
    search: "Ricerca",
    newTitle: "Scegli la nuova quotazione",
    newDesc: "Risultati per \"{query}\". {name} è quotato lì da ora; nome, acquisti, avvisi e sensori restano. Acquisti, vendite e avvisi di prezzo non vengono convertiti: in un'altra valuta le loro cifre valgono in quella. Se la valuta cambia, le statistiche a lungo termine dei suoi sensori ripartono da capo.",
    convert: "Converti in {base}",
    help: "Per una quotazione in un'altra valuta: tutto è mostrato in {base}, al tasso di riferimento della BCE.",
    helpHold: "Ciò che possiedi si inserisce allora anche in {base}.",
    currencyTitle: "Valuta",
    currencyDesc: "{name} è quotato in {quoted}. Se attivo, tutto è mostrato in {base}: il prezzo al tasso di riferimento della BCE del giorno, ogni punto del grafico al tasso del proprio giorno. Non è il prezzo a cui viene scambiato in {base}, e la variazione include quella della valuta. Acquisti, vendite e avvisi di prezzo già inseriti non vengono convertiti: le loro cifre valgono in {base} da quel momento. Se la valuta cambia, le statistiche a lungo termine dei suoi sensori ripartono da capo.",
    noRate: "La BCE non pubblica un tasso di riferimento per la valuta di questa quotazione, quindi non può essere convertita.",
  },
  ja: {
    venueTitle: "取引市場を変更",
    venueDesc: "{name} は {symbol} として登録されています。ISIN または名前でもう一度検索して、別の取引所やソースを選びます。",
    search: "検索",
    newTitle: "新しい取引市場を選択",
    newDesc: "「{query}」の検索結果です。{name} は今後そこで取得されます。名前、購入、アラート、センサーはそのまま残ります。購入、売却、価格アラートは換算されません。通貨が変わると、その数値は新しい通貨のものとして扱われます。通貨が変わる場合、センサーの長期統計は最初からやり直しになります。",
    convert: "{base} に換算",
    help: "別の通貨の取引市場向けです。すべての数値が ECB の参照レートで {base} で表示されます。",
    helpHold: "保有分も {base} で入力します。",
    currencyTitle: "通貨",
    currencyDesc: "{name} は {quoted} で取引されています。オンにすると、すべてが {base} で表示されます。価格は当日の ECB 参照レートで、チャートの各点はその日のレートで換算されます。{base} で実際に取引される価格ではなく、変動には通貨の変動も含まれます。入力済みの購入、売却、価格アラートは換算されず、その数値は以後 {base} として扱われます。通貨が変わる場合、センサーの長期統計は最初からやり直しになります。",
    noRate: "この取引市場の通貨には ECB の参照レートがないため、換算できません。",
  },
  lt: {
    venueTitle: "Keisti kotiravimą",
    venueDesc: "{name} įtraukta kaip {symbol}. Ieškokite jos dar kartą - pagal ISIN arba pavadinimą - ir pasirinkite kitą biržą ar šaltinį.",
    search: "Paieška",
    newTitle: "Pasirinkite naują kotiravimą",
    newDesc: "Rasta pagal „{query}“. {name} nuo šiol kotiruojama ten; pavadinimas, pirkimai, įspėjimai ir jutikliai lieka. Pirkimai, pardavimai ir kainos įspėjimai neperskaičiuojami - kita valiuta jų skaičiai laikomi tos valiutos. Jei valiuta pasikeičia, jutiklių ilgalaikė statistika pradedama iš naujo.",
    convert: "Perskaičiuoti į {base}",
    help: "Kotiravimui kita valiuta: viskas rodoma {base}, pagal ECB orientacinį kursą.",
    helpHold: "Tai, ką turite, tada taip pat įvedama {base}.",
    currencyTitle: "Valiuta",
    currencyDesc: "{name} kotiruojama {quoted}. Įjungus viskas rodoma {base}: kaina pagal tos dienos ECB orientacinį kursą, kiekvienas grafiko taškas pagal savo dienos kursą. Tai nėra kaina, kuria prekiaujama {base}, o pokytis apima ir valiutos pokytį. Jau įvesti pirkimai, pardavimai ir kainos įspėjimai neperskaičiuojami - jų skaičiai nuo tada laikomi {base}. Jei valiuta pasikeičia, jutiklių ilgalaikė statistika pradedama iš naujo.",
    noRate: "ECB neskelbia šio kotiravimo valiutos orientacinio kurso, todėl jos perskaičiuoti negalima.",
  },
  nb: {
    venueTitle: "Bytt notering",
    venueDesc: "{name} føres som {symbol}. Søk etter det på nytt - med ISIN eller navn - for å velge en annen børs eller kilde.",
    search: "Søk",
    newTitle: "Velg den nye noteringen",
    newDesc: "Funnet for \"{query}\". {name} føres der fra nå av; navn, kjøp, varsler og sensorer blir stående. Kjøp, salg og kursvarsler regnes ikke om - i en annen valuta gjelder tallene som den. Endres valutaen, begynner langtidsstatistikken for sensorene på nytt.",
    convert: "Regn om til {base}",
    help: "For en notering i en annen valuta: alt vises i {base}, til ESBs referansekurs.",
    helpHold: "Beholdningen legges da også inn i {base}.",
    currencyTitle: "Valuta",
    currencyDesc: "{name} noteres i {quoted}. Slått på vises alt i {base} i stedet: kursen til ESBs referansekurs for dagen, hvert punkt i grafen til kursen for sin egen dag. Det er ikke kursen det handles til i {base}, og endringen inneholder valutaens. Kjøp, salg og kursvarsler som allerede er lagt inn, regnes ikke om - tallene gjelder fra da av som {base}. Endres valutaen, begynner langtidsstatistikken for sensorene på nytt.",
    noRate: "ESB publiserer ingen referansekurs for valutaen til denne noteringen, så den kan ikke regnes om.",
  },
  nl: {
    venueTitle: "Notering wijzigen",
    venueDesc: "{name} staat genoteerd als {symbol}. Zoek het opnieuw - op ISIN of naam - om een andere beurs of bron te kiezen.",
    search: "Zoeken",
    newTitle: "Kies de nieuwe notering",
    newDesc: "Gevonden voor \"{query}\". {name} wordt vanaf nu daar genoteerd; naam, aankopen, alarmen en sensoren blijven. Aankopen, verkopen en koersalarmen worden niet omgerekend - in een andere valuta gelden hun bedragen als die valuta. Verandert de valuta, dan begint de langetermijnstatistiek van de sensoren opnieuw.",
    convert: "Omrekenen naar {base}",
    help: "Voor een notering in een andere valuta: alles wordt in {base} getoond, tegen de referentiekoers van de ECB.",
    helpHold: "Wat je bezit, voer je dan ook in {base} in.",
    currencyTitle: "Valuta",
    currencyDesc: "{name} is genoteerd in {quoted}. Ingeschakeld wordt alles in {base} getoond: de koers tegen de referentiekoers van de ECB van die dag, elk punt van de grafiek tegen de koers van zijn eigen dag. Dat is niet de koers waartegen het in {base} wordt verhandeld, en de verandering bevat die van de valuta. Al ingevoerde aankopen, verkopen en koersalarmen worden niet omgerekend - hun bedragen gelden vanaf dan als {base}. Verandert de valuta, dan begint de langetermijnstatistiek van de sensoren opnieuw.",
    noRate: "De ECB publiceert geen referentiekoers voor de valuta van deze notering, dus kan die niet worden omgerekend.",
  },
  pl: {
    venueTitle: "Zmień notowanie",
    venueDesc: "{name} jest notowany jako {symbol}. Wyszukaj go ponownie - po ISIN lub nazwie - aby wybrać inną giełdę lub źródło.",
    search: "Szukaj",
    newTitle: "Wybierz nowe notowanie",
    newDesc: "Znaleziono dla \"{query}\". {name} jest odtąd notowany tam; nazwa, zakupy, alerty i sensory zostają. Zakupy, sprzedaże i alerty cenowe nie są przeliczane - w innej walucie ich kwoty liczą się w niej. Jeśli waluta się zmienia, statystyki długoterminowe sensorów zaczynają się od nowa.",
    convert: "Przelicz na {base}",
    help: "Dla notowania w innej walucie: wszystko jest pokazywane w {base}, po kursie referencyjnym EBC.",
    helpHold: "To, co posiadasz, wpisujesz wtedy także w {base}.",
    currencyTitle: "Waluta",
    currencyDesc: "{name} jest notowany w {quoted}. Po włączeniu wszystko jest pokazywane w {base}: cena po kursie referencyjnym EBC z danego dnia, każdy punkt wykresu po kursie swojego dnia. To nie jest cena, po której jest notowany w {base}, a zmiana zawiera zmianę waluty. Wpisane już zakupy, sprzedaże i alerty cenowe nie są przeliczane - ich kwoty liczą się odtąd jako {base}. Jeśli waluta się zmienia, statystyki długoterminowe sensorów zaczynają się od nowa.",
    noRate: "EBC nie publikuje kursu referencyjnego dla waluty tego notowania, więc nie można jej przeliczyć.",
  },
  "pt-BR": {
    venueTitle: "Alterar a listagem",
    venueDesc: "{name} está listado como {symbol}. Pesquise-o de novo - pelo ISIN ou pelo nome - para escolher outra bolsa ou fonte.",
    search: "Pesquisa",
    newTitle: "Escolha a nova listagem",
    newDesc: "Encontrado para \"{query}\". {name} passa a ser cotado ali; o nome, as compras, os alertas e os sensores permanecem. Compras, vendas e alertas de preço não são convertidos - em outra moeda, os valores passam a valer nela. Se a moeda mudar, as estatísticas de longo prazo dos sensores recomeçam.",
    convert: "Converter para {base}",
    help: "Para uma listagem em outra moeda: tudo é mostrado em {base}, pela taxa de referência do BCE.",
    helpHold: "O que você tem também é informado em {base}.",
    currencyTitle: "Moeda",
    currencyDesc: "{name} é cotado em {quoted}. Ativado, tudo é mostrado em {base}: o preço pela taxa de referência do BCE do dia, cada ponto do gráfico pela taxa do seu próprio dia. Não é o preço pelo qual ele é negociado em {base}, e a variação inclui a da moeda. Compras, vendas e alertas de preço já informados não são convertidos - os valores passam a valer como {base}. Se a moeda mudar, as estatísticas de longo prazo dos sensores recomeçam.",
    noRate: "O BCE não publica taxa de referência para a moeda desta listagem, por isso ela não pode ser convertida.",
  },
  ru: {
    venueTitle: "Сменить листинг",
    venueDesc: "{name} значится как {symbol}. Найдите его снова - по ISIN или названию - и выберите другую биржу или источник.",
    search: "Поиск",
    newTitle: "Выберите новый листинг",
    newDesc: "Найдено по запросу «{query}». {name} теперь котируется там; название, покупки, оповещения и сенсоры остаются. Покупки, продажи и ценовые оповещения не пересчитываются - в другой валюте их числа считаются в ней. Если валюта меняется, долгосрочная статистика сенсоров начинается заново.",
    convert: "Пересчитывать в {base}",
    help: "Для листинга в другой валюте: всё показывается в {base}, по справочному курсу ЕЦБ.",
    helpHold: "То, чем вы владеете, тогда тоже вводится в {base}.",
    currencyTitle: "Валюта",
    currencyDesc: "{name} котируется в {quoted}. Если включено, всё показывается в {base}: цена по справочному курсу ЕЦБ на этот день, каждая точка графика по курсу своего дня. Это не цена, по которой он торгуется в {base}, и изменение включает изменение валюты. Уже введённые покупки, продажи и ценовые оповещения не пересчитываются - их числа с этого момента считаются в {base}. Если валюта меняется, долгосрочная статистика сенсоров начинается заново.",
    noRate: "ЕЦБ не публикует справочный курс для валюты этого листинга, поэтому пересчитать её нельзя.",
  },
  sk: {
    venueTitle: "Zmeniť kótovanie",
    venueDesc: "{name} je vedený ako {symbol}. Vyhľadajte ho znova - podľa ISIN alebo názvu - a vyberte inú burzu alebo zdroj.",
    search: "Hľadať",
    newTitle: "Vyberte nové kótovanie",
    newDesc: "Nájdené pre „{query}“. {name} je odteraz vedený tam; názov, nákupy, upozornenia a senzory zostávajú. Nákupy, predaje a cenové upozornenia sa neprepočítavajú - v inej mene platia ich čísla v nej. Ak sa mena zmení, dlhodobé štatistiky jeho senzorov začnú odznova.",
    convert: "Prepočítať na {base}",
    help: "Pre kótovanie v inej mene: všetko sa zobrazuje v {base}, podľa referenčného kurzu ECB.",
    helpHold: "To, čo držíte, sa potom tiež zadáva v {base}.",
    currencyTitle: "Mena",
    currencyDesc: "{name} je kótovaný v {quoted}. Po zapnutí sa všetko zobrazuje v {base}: cena podľa referenčného kurzu ECB daného dňa, každý bod grafu podľa kurzu svojho dňa. Nie je to cena, za ktorú sa obchoduje v {base}, a zmena zahŕňa aj zmenu meny. Už zadané nákupy, predaje a cenové upozornenia sa neprepočítavajú - ich čísla odvtedy platia ako {base}. Ak sa mena zmení, dlhodobé štatistiky jeho senzorov začnú odznova.",
    noRate: "Pre menu tohto kótovania ECB nezverejňuje referenčný kurz, preto ju nemožno prepočítať.",
  },
  sv: {
    venueTitle: "Byt notering",
    venueDesc: "{name} förs som {symbol}. Sök efter det igen - med ISIN eller namn - för att välja en annan börs eller källa.",
    search: "Sök",
    newTitle: "Välj den nya noteringen",
    newDesc: "Hittat för \"{query}\". {name} förs där från och med nu; namn, köp, larm och sensorer finns kvar. Köp, försäljningar och kurslarm räknas inte om - i en annan valuta gäller deras belopp som den. Ändras valutan börjar långtidsstatistiken för sensorerna om.",
    convert: "Räkna om till {base}",
    help: "För en notering i en annan valuta: allt visas i {base}, enligt ECB:s referenskurs.",
    helpHold: "Ditt innehav anges då också i {base}.",
    currencyTitle: "Valuta",
    currencyDesc: "{name} noteras i {quoted}. Påslaget visas allt i {base} i stället: kursen enligt ECB:s referenskurs för dagen, varje punkt i diagrammet enligt kursen för sin egen dag. Det är inte kursen det handlas till i {base}, och förändringen innehåller valutans. Köp, försäljningar och kurslarm som redan angetts räknas inte om - deras belopp gäller från och med då som {base}. Ändras valutan börjar långtidsstatistiken för sensorerna om.",
    noRate: "ECB publicerar ingen referenskurs för den här noteringens valuta, så den kan inte räknas om.",
  },
  tr: {
    venueTitle: "Kotasyonu değiştir",
    venueDesc: "{name}, {symbol} olarak kayıtlı. Başka bir borsa veya kaynak seçmek için onu yeniden arayın - ISIN veya adıyla.",
    search: "Arama",
    newTitle: "Yeni kotasyonu seçin",
    newDesc: "\"{query}\" için bulunanlar. {name} bundan sonra orada kote edilir; adı, alışları, alarmları ve sensörleri kalır. Alışlar, satışlar ve fiyat alarmları çevrilmez - başka bir para biriminde rakamları o para birimi sayılır. Para birimi değişirse sensörlerinin uzun dönem istatistikleri baştan başlar.",
    convert: "{base} cinsine çevir",
    help: "Başka para birimindeki bir kotasyon için: her şey AMB referans kuruyla {base} olarak gösterilir.",
    helpHold: "Elinizdekiler de o zaman {base} olarak girilir.",
    currencyTitle: "Para birimi",
    currencyDesc: "{name}, {quoted} cinsinden kote edilir. Açıkken her şey {base} olarak gösterilir: fiyat günün AMB referans kuruyla, grafiğin her noktası kendi gününün kuruyla. Bu, {base} cinsinden işlem gördüğü fiyat değildir ve değişim para biriminin değişimini de içerir. Daha önce girilmiş alışlar, satışlar ve fiyat alarmları çevrilmez - rakamları o andan itibaren {base} sayılır. Para birimi değişirse sensörlerinin uzun dönem istatistikleri baştan başlar.",
    noRate: "AMB bu kotasyonun para birimi için referans kuru yayımlamıyor, bu yüzden çevrilemez.",
  },
  "zh-Hans": {
    venueTitle: "更换上市地",
    venueDesc: "{name} 当前以 {symbol} 记录。请按 ISIN 或名称重新搜索，以选择其他交易所或来源。",
    search: "搜索",
    newTitle: "选择新的上市地",
    newDesc: "“{query}”的搜索结果。{name} 今后在该处取价；其名称、买入、提醒和传感器保持不变。买入、卖出和价格提醒不会换算：币种不同时，其数值按新币种计。币种变化时，其传感器的长期统计重新开始。",
    convert: "换算为 {base}",
    help: "适用于其他币种的上市地：所有数值按欧洲央行参考汇率以 {base} 显示。",
    helpHold: "持仓也以 {base} 录入。",
    currencyTitle: "币种",
    currencyDesc: "{name} 以 {quoted} 报价。开启后，所有数值改以 {base} 显示：价格按当日欧洲央行参考汇率换算，图表上的每个点按其当日汇率换算。这不是它以 {base} 交易的价格，涨跌也包含汇率变动。已录入的买入、卖出和价格提醒不会换算，其数值此后按 {base} 计。币种变化时，其传感器的长期统计重新开始。",
    noRate: "欧洲央行未公布该上市地币种的参考汇率，因此无法换算。",
  },
};

for (const [code, t] of Object.entries(T)) {
  const file = path.join(dir, "out", `${code}.backend.json`);
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  const node = data.config_subentries.instrument;
  const step = node.step;
  const menu = {};
  for (const [key, value] of Object.entries(step.reconfigure.menu_options)) {
    if (key === "venue" || key === "currency") continue;
    menu[key] = value;
    if (key === "rename") menu.venue = `🏛️ ${t.venueTitle}`;
    if (key === "color") menu.currency = `💱 ${t.currencyTitle}`;
  }
  step.reconfigure.menu_options = menu;
  step.listing.data.convert = t.convert;
  step.listing.data_description = { ...(step.listing.data_description || {}), convert: `${t.help} ${t.helpHold}` };
  const steps = {};
  for (const [key, value] of Object.entries(step)) {
    if (key === "venue" || key === "venue_listing" || key === "currency") continue;
    steps[key] = value;
    if (key === "rename") {
      steps.venue = { title: t.venueTitle, description: t.venueDesc, data: { query: t.search } };
      steps.venue_listing = {
        title: t.newTitle,
        description: t.newDesc,
        data: { listing: step.listing.data.listing, convert: t.convert },
        data_description: { convert: t.help },
      };
    }
    if (key === "color") {
      steps.currency = { title: t.currencyTitle, description: t.currencyDesc, data: { convert: t.convert } };
    }
  }
  node.step = steps;
  node.error = { ...(node.error || {}), no_rate: t.noRate };
  fs.writeFileSync(file, JSON.stringify(data, null, 4) + "\n");
}
console.log("written: " + Object.keys(T).join(", "));

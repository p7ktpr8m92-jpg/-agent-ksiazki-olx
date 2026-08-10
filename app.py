
import base64, io, json, re
from pathlib import Path

import requests
import streamlit as st
from PIL import Image
from openai import OpenAI

st.set_page_config(page_title="Agent książek → OLX", page_icon="📚", layout="centered")

st.title("📚 Agent książek → OLX")
st.caption("MVP: zdjęcia → rozpoznanie → wycena → gotowe ogłoszenie. Publikowanie na OLX podłączymy po uzyskaniu oficjalnego dostępu.")

with st.sidebar:
    st.header("Ustawienia")
    api_key = st.text_input("OpenAI API key", type="password",
                            help="Klucz jest używany tylko podczas tego uruchomienia aplikacji.")
    model = st.text_input("Model", value="gpt-5.6")
    st.divider()
    st.markdown("**Ważne:** nie wpisuj tu hasła do OLX ani Client Secret.")

files = st.file_uploader(
    "📸 Dodaj 1–4 zdjęcia książki",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True
)

condition = st.selectbox(
    "Stan książki",
    ["Nie wiem — oceń ze zdjęć", "Jak nowa", "Bardzo dobry", "Dobry", "Dostateczny"]
)

comparables = st.text_input(
    "Ceny podobnych egzemplarzy (opcjonalnie)",
    placeholder="np. 15, 19.99, 24.90, 29.00"
)

shipping = st.multiselect(
    "Wysyłka",
    ["OLX Przesyłka", "Paczkomat", "Kurier", "Odbiór osobisty"],
    default=["OLX Przesyłka"]
)

def img_to_data_url(uploaded):
    img = Image.open(uploaded).convert("RGB")
    img.thumbnail((1800, 1800))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return "data:image/jpeg;base64," + b64

def google_books_lookup(title="", author="", isbn=""):
    queries = []
    if isbn:
        queries.append(f"isbn:{isbn.replace('-', '')}")
    if title and author:
        queries.append(f'intitle:"{title}" inauthor:"{author}"')
    if title:
        queries.append(f'intitle:"{title}"')
    for q in queries:
        try:
            r = requests.get(
                "https://www.googleapis.com/books/v1/volumes",
                params={"q": q, "maxResults": 5},
                timeout=8,
            )
            if not r.ok:
                continue
            data = r.json()
            if data.get("items"):
                return data["items"][0].get("volumeInfo", {})
        except Exception:
            pass
    return {}

if st.button("🤖 Rozpoznaj książkę i przygotuj ogłoszenie", type="primary", use_container_width=True):
    if not files:
        st.error("Dodaj przynajmniej jedno zdjęcie.")
        st.stop()
    if not api_key:
        st.error("Wpisz OpenAI API key w panelu po lewej.")
        st.stop()

    client = OpenAI(api_key=api_key)

    image_inputs = [{"type": "input_image", "image_url": img_to_data_url(f)} for f in files]
    prompt = f"""
Jesteś agentem sprzedaży używanych książek w Polsce.
Na podstawie zdjęć zidentyfikuj konkretny egzemplarz. Nie zgaduj numeru ISBN, jeśli nie da się go odczytać.
Oceń stan wyłącznie na podstawie widocznych elementów i zaznacz niepewność.
Stan podany przez użytkownika: {condition}.
Opcjonalne ceny podobnych egzemplarzy: {comparables or "brak"}.
Preferowana wysyłka: {", ".join(shipping) if shipping else "brak"}.

Zwróć WYŁĄCZNIE poprawny JSON:
{{
  "title": "...",
  "author": "...",
  "publisher": "...",
  "year": null,
  "isbn": "...",
  "language": "pl",
  "edition_notes": "...",
  "condition": "...",
  "condition_confidence": 0.0,
  "identification_confidence": 0.0,
  "description": "...",
  "suggested_price_pln": 0.0,
  "quick_sale_price_pln": 0.0,
  "minimum_reasonable_price_pln": 0.0,
  "category": "Książki",
  "tags": ["..."],
  "missing_information": ["..."]
}}

Cena ma być realistyczną ESTYMACJĄ, nie przedstawiaj jej jako aktualnego wyniku z OLX.
Opis ma być rzeczowy i nie może wymyślać wad ani zalet, których nie widać.
"""
    with st.spinner("Analizuję zdjęcia…"):
        try:
            response = client.responses.create(
                model=model,
                input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}, *image_inputs]}],
            )
            raw = response.output_text.strip()
            raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.I)
            data = json.loads(raw)
        except Exception as e:
            st.error(f"Nie udało się przetworzyć odpowiedzi: {e}")
            st.stop()

    # Potwierdzenie bibliograficzne przez Google Books, jeśli mamy dane.
    gb = google_books_lookup(data.get("title",""), data.get("author",""), data.get("isbn",""))
    if gb:
        data["_google_books_check"] = {
            "title": gb.get("title"),
            "authors": gb.get("authors"),
            "publisher": gb.get("publisher"),
            "publishedDate": gb.get("publishedDate"),
            "industryIdentifiers": gb.get("industryIdentifiers"),
        }

    st.session_state["listing"] = data

if "listing" in st.session_state:
    d = st.session_state["listing"]
    st.divider()
    st.subheader("✅ Wynik agenta")

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Cena wystawienia", f'{d.get("suggested_price_pln", 0):.2f} zł')
    with c2:
        st.metric("Cena szybkiej sprzedaży", f'{d.get("quick_sale_price_pln", 0):.2f} zł')

    st.write(f"**Identyfikacja:** {d.get('title','')} — {d.get('author','')}")
    st.write(f"**ISBN:** {d.get('isbn') or 'nieodczytany'}")
    st.write(f"**Stan:** {d.get('condition','')} (pewność: {d.get('condition_confidence',0):.0%})")
    st.write(f"**Pewność identyfikacji:** {d.get('identification_confidence',0):.0%}")

    st.subheader("Tytuł OLX")
    st.code(d.get("title",""), language=None)

    st.subheader("Opis OLX")
    st.text_area("Gotowy opis", d.get("description",""), height=230, label_visibility="collapsed")

    st.subheader("Kategoria")
    st.write(d.get("category","Książki"))

    if d.get("tags"):
        st.write("**Tagi:** " + " ".join("#"+str(x).lstrip("#") for x in d["tags"]))

    if d.get("missing_information"):
        st.warning("Do weryfikacji: " + ", ".join(d["missing_information"]))

    if d.get("_google_books_check"):
        with st.expander("Weryfikacja bibliograficzna"):
            st.json(d["_google_books_check"])

    export = {
        "olx_title": d.get("title"),
        "olx_description": d.get("description"),
        "price_pln": d.get("suggested_price_pln"),
        "category": d.get("category"),
        "isbn": d.get("isbn"),
        "author": d.get("author"),
        "publisher": d.get("publisher"),
        "year": d.get("year"),
        "condition": d.get("condition"),
        "shipping": shipping,
        "status": "READY_FOR_OLX",
    }
    st.download_button(
        "⬇️ Pobierz dane ogłoszenia (JSON)",
        data=json.dumps(export, ensure_ascii=False, indent=2),
        file_name="ogloszenie_olx.json",
        mime="application/json",
        use_container_width=True,
    )
    st.divider()
    st.subheader("🟠 Gotowe do wystawienia")

    st.link_button(
        "🟠 Wystaw na OLX",
        "https://www.olx.pl/d/nowe-ogloszenie/",
        use_container_width=True
    )

    st.caption(
        "OLX otworzy formularz nowego ogłoszenia. "
        "Skopiuj przygotowany wyżej tytuł, opis i cenę."
    )

        st.caption(
            "OLX otworzy formularz nowego ogłoszenia. "
            "Skopiuj przygotowany wyżej tytuł, opis i cenę."
        )
    st.info("Następny moduł: oficjalne połączenie z OLX, jeśli konto/aplikacja otrzyma dostęp do Partner API. Nie obchodzimy zabezpieczeń OLX.")

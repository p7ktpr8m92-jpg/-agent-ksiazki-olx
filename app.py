import base64
import io
import json
import re

import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from openai import OpenAI


st.set_page_config(
    page_title="Agent książek → OLX",
    page_icon="📚",
    layout="centered",
)

st.title("📚 Agent książek → OLX")
st.caption(
    "Zdjęcia → rozpoznanie → wycena → gotowe ogłoszenie → OLX"
)


with st.sidebar:
    st.header("Ustawienia")

    api_key = st.text_input(
        "OpenAI API key",
        type="password",
    )

    model = st.text_input(
        "Model",
        value="gpt-5.6",
    )

    st.divider()
    st.markdown(
        "**Nie wpisuj tutaj hasła do OLX.**"
    )


files = st.file_uploader(
    "📸 Dodaj 1–4 zdjęcia książki",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)

condition = st.selectbox(
    "Stan książki",
    [
        "Nie wiem — oceń ze zdjęć",
        "Jak nowa",
        "Bardzo dobry",
        "Dobry",
        "Dostateczny",
    ],
)

comparables = st.text_input(
    "Ceny podobnych egzemplarzy (opcjonalnie)",
    placeholder="np. 15, 19.99, 24.90, 29.00",
)

shipping = st.multiselect(
    "Wysyłka",
    [
        "OLX Przesyłka",
        "Paczkomat",
        "Kurier",
        "Odbiór osobisty",
    ],
    default=["OLX Przesyłka"],
)


def img_to_data_url(uploaded):
    img = Image.open(uploaded).convert("RGB")
    img.thumbnail((1800, 1800))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)

    b64 = base64.b64encode(
        buf.getvalue()
    ).decode()

    return "data:image/jpeg;base64," + b64


def google_books_lookup(
    title="",
    author="",
    isbn="",
):
    queries = []

    if isbn:
        queries.append(
            f"isbn:{isbn.replace('-', '')}"
        )

    if title and author:
        queries.append(
            f'intitle:"{title}" inauthor:"{author}"'
        )

    if title:
        queries.append(
            f'intitle:"{title}"'
        )

    for q in queries:
        try:
            r = requests.get(
                "https://www.googleapis.com/books/v1/volumes",
                params={
                    "q": q,
                    "maxResults": 5,
                },
                timeout=8,
            )

            if not r.ok:
                continue

            data = r.json()

            if data.get("items"):
                return (
                    data["items"][0]
                    .get("volumeInfo", {})
                )

        except Exception:
            pass

    return {}


def copy_button(
    label,
    text,
    key,
):
    safe_text = json.dumps(
        str(text),
        ensure_ascii=False,
    )

    html = f"""
    <button id="{key}"
        style="
        width:100%;
        padding:12px;
        border-radius:10px;
        border:1px solid #777;
        background:transparent;
        font-size:16px;
        cursor:pointer;
        ">
        📋 {label}
    </button>

    <div id="{key}_msg"
        style="
        margin-top:6px;
        font-size:13px;
        ">
    </div>

    <script>

    const btn =
        document.getElementById("{key}");

    const msg =
        document.getElementById(
            "{key}_msg"
        );

    const text = {safe_text};

    btn.addEventListener(
        "click",
        async () => {{

            try {{

                await navigator.clipboard
                    .writeText(text);

                msg.textContent =
                    "Skopiowano ✅";

            }} catch (e) {{

                msg.textContent =
                    "Nie udało się skopiować.";

            }}

        }}
    );

    </script>
    """

    components.html(
        html,
        height=75,
    )


if st.button(
    "🤖 Rozpoznaj książkę i przygotuj ogłoszenie",
    type="primary",
    use_container_width=True,
):

    if not files:
        st.error(
            "Dodaj przynajmniej jedno zdjęcie."
        )
        st.stop()

    if not api_key:
        st.error(
            "Wpisz OpenAI API key w panelu po lewej."
        )
        st.stop()

    client = OpenAI(
        api_key=api_key
    )

    image_inputs = []

    for f in files:

        image_inputs.append(
            {
                "type": "input_image",
                "image_url": img_to_data_url(f),
            }
        )

    prompt = f"""
Jesteś agentem sprzedaży używanych książek w Polsce.

Na podstawie zdjęć rozpoznaj książkę.

Nie zgaduj ISBN, jeśli nie da się go odczytać.

Oceń stan tylko na podstawie tego,
co faktycznie widać na zdjęciach.

Stan podany przez użytkownika:
{condition}

Ceny podobnych egzemplarzy:
{comparables or "brak"}

Wysyłka:
{", ".join(shipping)}

Zwróć WYŁĄCZNIE poprawny JSON:

{{
"title": "",
"author": "",
"publisher": "",
"year": null,
"isbn": "",
"condition": "",
"condition_confidence": 0.0,
"identification_confidence": 0.0,
"description": "",
"suggested_price_pln": 0.0,
"quick_sale_price_pln": 0.0,
"category": "Książki",
"tags": [],
"missing_information": []
}}

Cena jest estymacją.

Nie wymyślaj informacji,
których nie widać na zdjęciach.
"""

    with st.spinner(
        "Analizuję zdjęcia…"
    ):

        try:

            response = (
                client.responses.create(
                    model=model,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": prompt,
                                },
                                *image_inputs,
                            ],
                        }
                    ],
                )
            )

            raw = (
                response.output_text
                .strip()
            )

            raw = re.sub(
                r"^```json\s*|\s*```$",
                "",
                raw,
                flags=re.I,
            )

            data = json.loads(raw)

        except Exception as e:

            st.error(
                f"Błąd analizy: {e}"
            )

            st.stop()


    gb = google_books_lookup(
        data.get("title", ""),
        data.get("author", ""),
        data.get("isbn", ""),
    )

    if gb:

        data["_google_books_check"] = {
            "title":
                gb.get("title"),

            "authors":
                gb.get("authors"),

            "publisher":
                gb.get("publisher"),

            "publishedDate":
                gb.get("publishedDate"),
        }


    st.session_state[
        "listing"
    ] = data


if "listing" in st.session_state:

    d = st.session_state[
        "listing"
    ]

    st.divider()

    st.subheader(
        "✅ Wynik agenta"
    )


    col1, col2 = st.columns(2)


    with col1:

        st.metric(
            "Cena wystawienia",
            f'{d.get("suggested_price_pln", 0)} zł',
        )


    with col2:

        st.metric(
            "Cena szybkiej sprzedaży",
            f'{d.get("quick_sale_price_pln", 0)} zł',
        )


    st.write(
        f"**Identyfikacja:** "
        f"{d.get('title', '')} — "
        f"{d.get('author', '')}"
    )


    st.write(
        f"**ISBN:** "
        f"{d.get('isbn') or 'nieodczytany'}"
    )


    st.write(
        f"**Stan:** "
        f"{d.get('condition', '')}"
    )


    st.subheader(
        "Tytuł OLX"
    )

    st.code(
        d.get("title", ""),
        language=None,
    )


    st.subheader(
        "Opis OLX"
    )

    st.text_area(
        "Gotowy opis",
        d.get("description", ""),
        height=230,
        label_visibility="collapsed",
    )


    st.subheader(
        "Kategoria"
    )

    st.write(
        d.get(
            "category",
            "Książki",
        )
    )


    if d.get(
        "missing_information"
    ):

        st.warning(
            "Do weryfikacji: "
            + ", ".join(
                d[
                    "missing_information"
                ]
            )
        )


    if d.get(
        "_google_books_check"
    ):

        with st.expander(
            "Weryfikacja bibliograficzna"
        ):

            st.json(
                d[
                    "_google_books_check"
                ]
            )


    st.divider()

    st.subheader(
        "🟠 Gotowe do wystawienia"
    )


    title = d.get(
        "title",
        "",
    )

    description = d.get(
        "description",
        "",
    )

    price = d.get(
        "suggested_price_pln",
        "",
    )


    st.markdown(
        "### Tytuł"
    )

    st.code(
        title,
        language=None,
    )

    copy_button(
        "Kopiuj tytuł",
        title,
        "copy_title",
    )


    st.markdown(
        "### Cena"
    )

    st.code(
        f"{price} zł",
        language=None,
    )

    copy_button(
        "Kopiuj cenę",
        price,
        "copy_price",
    )


    st.markdown(
        "### Opis"
    )

    st.text_area(
        "Opis do OLX",
        description,
        height=250,
    )

    copy_button(
        "Kopiuj opis",
        description,
        "copy_description",
    )


    st.link_button(
        "🟠 Otwórz formularz OLX",
        "https://www.olx.pl/d/nowe-ogloszenie/",
        use_container_width=True,
    )


    st.caption(
        "Skopiuj tytuł, cenę i opis, "
        "a następnie wklej je do OLX."
    )

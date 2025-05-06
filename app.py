import pandas as pd
import streamlit as st
import re
from datetime import datetime
import os
import tempfile

# Načtení defaultních souborů z kořenového adresáře
@st.cache_data
def nacti_defaultni_soubory():
    try:
        vzor = pd.read_excel('vzor.xlsx')
        vazby_znacek = pd.read_excel('vazby_znacek.xlsx', dtype={'A': str})
        return vzor, vazby_znacek
    except Exception as e:
        st.error(f"Chyba při načítání defaultních souborů: {e}")
        return None, None

# Pomocná funkce pro bezpečné načtení souboru
def bezpecne_nacteni_excel(uploaded_file):
    try:
        # Vytvoříme dočasný soubor, abychom obešli potenciální problémy s názvem souboru
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        # Načteme Excel soubor z dočasného umístění
        df = pd.read_excel(tmp_path)
        
        # Smažeme dočasný soubor
        os.unlink(tmp_path)
        
        return df
    except Exception as e:
        st.error(f"Chyba při načítání souboru: {e}")
        return None

# Hlavní funkce pro zpracování
def zpracuj_soubory(vazby_produktu, vazby_akci, zlm):
    vzor, vazby_znacek = nacti_defaultni_soubory()
    if vzor is None or vazby_znacek is None:
        return None

    vysledek = pd.DataFrame(columns=vzor.columns)
    
    # Přidána kontrola prázdných dataframů
    if vazby_akci.empty:
        st.error("Soubor s vazbami akcí neobsahuje žádná data.")
        return None
    
    # Kontrola indexů a formátu dat
    try:
        for _, radek_akce in vazby_akci.iterrows():
            if len(radek_akce) <= 6:
                st.warning(f"Přeskakuji neplatný řádek v souboru vazeb akcí - nedostatek sloupců.")
                continue
                
            try:
                id_dlazdice = radek_akce.iloc[1]
                if pd.isna(id_dlazdice):
                    continue
            except IndexError:
                st.warning("Chybí sloupec s ID dlaždice v souboru vazeb akcí.")
                continue
            
            novy_radek = {}
            
            # Získání kódů zboží s ošetřením prázdných hodnot
            filtrovane_radky = vazby_produktu[vazby_produktu.iloc[:, 2] == id_dlazdice]
            obicis_list = filtrovane_radky.iloc[:, 0].tolist() if not filtrovane_radky.empty else []
            
            kody_zbozi = []
            for obicis in obicis_list:
                if pd.isna(obicis):
                    continue
                    
                radky_zlm = zlm[zlm.iloc[:, 2] == obicis]
                if not radky_zlm.empty:
                    try:
                        kod_hodnota = radky_zlm.iloc[0, 1]
                        if pd.notna(kod_hodnota):
                            kod_zbozi = str(kod_hodnota).split('.')[0].zfill(18)
                            kody_zbozi.append(kod_zbozi)
                    except (IndexError, AttributeError) as e:
                        st.warning(f"Problém při zpracování kódu zboží: {e}")
            
            # Klubová akce
            klubova_akce = 0
            for obicis in obicis_list:
                if pd.isna(obicis):
                    continue
                    
                radky_zlm = zlm[zlm.iloc[:, 2] == obicis]
                if not radky_zlm.empty:
                    try:
                        znacka_hodnota = radky_zlm.iloc[0, 12]
                        if pd.notna(znacka_hodnota) and str(znacka_hodnota).strip().upper().startswith("MK"):
                            klubova_akce = 1
                            break
                    except IndexError:
                        pass
            
            # ID značky s ošetřením chybějících hodnot
            try:
                nazev_znacky = radek_akce.iloc[6]
                if pd.isna(nazev_znacky):
                    id_znacky = ""
                else:
                    znacka_radky = vazby_znacek[vazby_znacek.iloc[:, 2].str.lower() == str(nazev_znacky).lower()]
                    id_znacky = znacka_radky.iloc[0, 0] if not znacka_radky.empty else ""
            except (IndexError, AttributeError):
                id_znacky = ""
            
            # Určení hodnoty pro sloupec D na základě slugu
            slug = str(id_dlazdice).lower() if pd.notna(id_dlazdice) else ""
            if slug.startswith("te"):
                column_d_value = "leaflet"
            elif slug.startswith("ma"):
                column_d_value = "magazine"
            elif slug.startswith("dz"):
                column_d_value = "longTermDiscount"
            elif slug.startswith("kp"):
                column_d_value = "coupons"
            else:
                column_d_value = "leaflet"  # Výchozí hodnota
            
            # Bezpečné získání hodnot
            def bezpecny_pristup(dataframe, index, default=""):
                try:
                    hodnota = dataframe.iloc[index]
                    return "" if pd.isna(hodnota) else hodnota
                except IndexError:
                    return default
            
            # Sestavení řádku s ošetřením indexů
            novy_radek = {
                vzor.columns[0]: 1,
                vzor.columns[1]: klubova_akce,
                vzor.columns[2]: bezpecny_pristup(radek_akce, 5),
                vzor.columns[3]: column_d_value,
                vzor.columns[4]: bezpecny_pristup(radek_akce, 16) if len(radek_akce) > 16 else "",
                vzor.columns[5]: slug,
                vzor.columns[6]: bezpecny_pristup(radek_akce, 2),
                vzor.columns[7]: bezpecny_pristup(radek_akce, 4),
                vzor.columns[8]: f"{str(id_dlazdice).upper()}.jpg" if pd.notna(id_dlazdice) else "",
                vzor.columns[9]: id_znacky,
                vzor.columns[10]: ','.join(kody_zbozi)
            }
            
            vysledek = pd.concat([vysledek, pd.DataFrame([novy_radek])], ignore_index=True)
    except Exception as e:
        st.error(f"Chyba při zpracování dat: {e}")
        return None
    
    return vysledek

# Streamlit UI
st.title("Generátor marketingových akcí")
st.write("Nahrajte 3 požadované soubory ve formátu XLSX:")

vazby_produktu_file = st.file_uploader("1. Soubor VAZBY produktu", type="xlsx")
vazby_akci_file = st.file_uploader("2. Soubor KEN (vazby akcí)", type="xlsx")
zlm_file = st.file_uploader("3. Soubor ZLM", type="xlsx")

if st.button("Spustit generování"):
    if all([vazby_produktu_file, vazby_akci_file, zlm_file]):
        try:
            with st.spinner('Zpracovávám data...'):
                # Použijeme bezpečnou metodu načtení
                vazby_produktu = bezpecne_nacteni_excel(vazby_produktu_file)
                vazby_akci = bezpecne_nacteni_excel(vazby_akci_file)
                zlm = bezpecne_nacteni_excel(zlm_file)
                
                if any(df is None for df in [vazby_produktu, vazby_akci, zlm]):
                    st.error("Některé soubory se nepodařilo načíst.")
                else:
                    vysledek = zpracuj_soubory(vazby_produktu, vazby_akci, zlm)
                    
                    if vysledek is not None and not vysledek.empty:
                        try:
                            csv = vysledek.to_csv(index=False, sep=';', encoding='utf-8-sig')
                            st.success("Generování úspěšně dokončeno!")
                            st.download_button(
                                label="Stáhnout výsledný soubor",
                                data=csv,
                                file_name=f"vysledek_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                mime="text/csv"
                            )
                        except Exception as e:
                            st.error(f"Chyba při exportu CSV: {str(e)}")
                    else:
                        st.error("Nepodařilo se vygenerovat výsledek. Zkontrolujte formát vstupních souborů.")
        except Exception as e:
            st.error(f"Došlo k chybě: {str(e)}")
    else:
        st.warning("Prosím, nahrajte všechny požadované soubory!")

---
title: Dashboard Grafana Ingestion
---

Tableau de bord Grafana --- Monitoring microservice d'ingestion  
  
**1) Vue d'ensemble --- Ingestion: Health**  
1 Statuts dernière exécution : Succès (N), Échecs (N), Taux d'échec (%),
p95 durée (s), Max  
mémoire (MB).  
2 Timeline des runs (barre empilée par Etat).  
3 Top sources par durée (p95).  
4 Derniers messages d'erreur (table des 5 derniers FAILED avec
détails).  
  
**2) Fiabilité --- Errors & SLAs**  
1 Taux d'échec (global et par Source).  
2 MTTR (Mean Time To Recovery).  
3 SLO de fraîcheur : alerte si pas de run \> X minutes.  
  
**3) Performance --- Latency & Throughput**  
1 Durées : p50/p95/p99 de Duree secondes par Source et Objet.  
2 Débit : nb d'exécutions / 5 min par Source.  
3 CPU & mémoire : p95 par Source.  
  
**4) Détails par connecteur --- Sources & Objets**  
Grille filtrable avec colonnes : Debut, Fin, Duree secondes, cpu_time,
memory_used, Description.  
  
**5) Règles d'alerte (exemples)**  
1 Échec détecté (critique) : \>0 FAILED sur 5 minutes.  
2 Taux d'échec élevé : \>2% pendant 15 minutes.  
3 Source muette : pas d'occurrence sur 75 minutes.  
4 Latence p95 dégradée : p95 \> 2× baseline.  
5 Surconsommation mémoire/CPU : mémoire \>150 MB ou CPU \>60s (p95).  
6 Burst d'erreurs sur un Objet : \>3 erreurs sur 10 minutes.  
  
**6) Exemple de visuel du dashboard**  
- Panel Type Exemple de métrique  
- Success / Failed Stat Succès=120, Échecs=3  
- Taux d'échec Stat (%) 2.4 %  
- Durée (p95) Time series 2.3s  
- Dernières erreurs Table Source=A, Objet=X, Desc=timeout

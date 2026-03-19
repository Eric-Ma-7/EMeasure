from emeasure.saver import SqliteSaver

saver = SqliteSaver(
    db_path="my_data.db", experiment_name="Scan_IV_Curve", 
    meta={
        "I_ports": "P1-P4", "V_ports": "P2-P3",
        "Temperature": 300
    }
)

for i in range(10):
    saver.add({
        'current': i,
        'voltage': i ** 2
    })
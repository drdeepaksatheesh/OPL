const DB_NAME = "openphysiologylab-reference-data";
const DB_VERSION = 1;
const STORE = "records";

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, {keyPath: "record_id"});
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function saveRecord(record) {
  const db = await openDb();
  await transactionPromise(db, "readwrite", store => store.put(record));
  db.close();
}

export async function getRecord(recordId) {
  const db = await openDb();
  const value = await requestPromise(db.transaction(STORE, "readonly").objectStore(STORE).get(recordId));
  db.close();
  return value || null;
}

export async function listRecords() {
  const db = await openDb();
  const value = await requestPromise(db.transaction(STORE, "readonly").objectStore(STORE).getAll());
  db.close();
  return value || [];
}

export async function deleteRecord(recordId) {
  const db = await openDb();
  await transactionPromise(db, "readwrite", store => store.delete(recordId));
  db.close();
}

function transactionPromise(db, mode, action) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    action(tx.objectStore(STORE));
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

function requestPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

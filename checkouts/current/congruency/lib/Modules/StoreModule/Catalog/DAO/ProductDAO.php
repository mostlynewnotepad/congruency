<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
if(!class_exists("ProductDAO")){
	class ProductDAO extends AbstractDAO{

		public function __construct(){
			$this->table = "Products";   // #79: sqlite table is `Products` (was MySQL db.table "paw.product" -> "no such table"); matches CatalogDAO/PriceDAO/seed
			$this->dataConnection = DataConnection::CreateConnection(MYSQL_SERVER,MYSQL_STORE_DATABASE,STORE_LOGIN,STORE_PASSWORD);   // BUG-02: open a connection like sibling DAOs
			$this->dataConnection->open();
		}

		public function obtainRow($key){
			$key = ValidateFields::validateNumericKey($key);
			if(isset($key)){
   	    		$selectString = "WHERE `key`=". $key;
				$rows = $this->select($selectString);
				$beansArray = $this->returnAllBeans($rows);
				return current($beansArray);
			}
		}

		public function obtainNRows($groupKey){
   	    	$groupKey = ValidateFields::validateNumericKey($groupKey);
   	    	$selectString = "WHERE `category`=".$groupKey;
			$rows = $this->select($selectString);
			return $this->returnAllBeans($rows);
		}

		public function obtainAllRows(){
			$rows = $this->select("");
			return $this->returnAllBeans($rows);
		}

		public function deleteRow($itemKey){
   	    	$itemKey = ValidateFields::validateNumericKey($itemKey);
			if(isset($itemKey)){
				$this->delete("WHERE `key`=$itemKey");
			}
		}

		public function insertRow($rowData){
			if(!empty($rowData)){
				foreach($rowData as &$value){
					$value = $this->quote($value);
				}
				//$results['index'] = "LAST_INSERT_ID()"; //MAGIC:: Seems as if mysql does this...
				$insertString = $this->buildInsertSQL($rowData);
				$this->query($insertString);
			}
		}

		public function updateRow($rowData){
			$this->deleteRow($rowData['key']);
			$this->insertRow($rowData);
		}


		public function getBean($row){
			$bean = new Product();
			$bean->setCategory($row['category']);
			$bean->setName($row['name']);
			$bean->setDescription($row['description']);
			$bean->setKey($row['key']);
			$bean->setPage($row['page']);
			$bean->setPicture($row['picture']);
			return $bean;
		}

	}
}
?>
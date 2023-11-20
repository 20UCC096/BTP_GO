package main

import "fmt"

func main() {
	var x int = 10
	var err = "error"

	if x > 0 {
		if x==10{
			x += 10
		} else {
			x -= 10
		}
		
		x = 5

		if x==10{
			x += 10
		} else {
			x -= 10
		}
	} else {
		err = "ok"
	}

}
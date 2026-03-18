module github.com/beltxa/acp/tools/poker-demo/go-player

go 1.23.0

require github.com/beltxa/acp/sdks/go v0.0.0

require (
	github.com/eclipse/paho.mqtt.golang v1.5.0 // indirect
	github.com/google/uuid v1.6.0 // indirect
	github.com/gorilla/websocket v1.5.3 // indirect
	github.com/rabbitmq/amqp091-go v1.10.0 // indirect
	golang.org/x/crypto v0.39.0 // indirect
	golang.org/x/net v0.27.0 // indirect
	golang.org/x/sync v0.7.0 // indirect
)

replace github.com/beltxa/acp/sdks/go => ../../../sdks/go
